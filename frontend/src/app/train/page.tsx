"use client";

import {
  ArrowLeft,
  ArrowRight,
  Brain,
  CheckCircle2,
  Database,
  Eye,
  Lightbulb,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { api } from "@/lib/api";
import { conceptLabel, type ECGPoint } from "@/lib/coordinates";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
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
  focusGrounded: boolean;
  grade: Record<string, unknown>;
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

const CAMPAIGN_LENGTHS = [10, 25, 50, 100, 500, 1000, 5000] as const;

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
};

const TRAINING_SUBSKILLS: Array<{ id: LearningSubskill; label: string }> = [
  { id: "recognize", label: "Recognize the pattern" },
  { id: "localize", label: "Localize the evidence" },
  { id: "measure", label: "Measure it" },
  { id: "discriminate", label: "Distinguish a close mimic" },
  { id: "explain_mechanism", label: "Explain the mechanism" },
  { id: "synthesize", label: "Synthesize the finding" },
  { id: "apply_in_context", label: "Apply it in context" },
  { id: "calibrate_confidence", label: "Calibrate confidence" },
];

function isLearningSubskill(value: string): value is LearningSubskill {
  return TRAINING_SUBSKILLS.some((item) => item.id === value);
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function sourceLabel(source?: string) {
  if (source === "fixture") return "Non-clinical demo fixture";
  if (source === "prepared_bundle") return "Prepared PTB-XL bundle";
  if (source === "ptbxl") return "PTB-XL + PTB-XL+";
  if (source === "leipzig-heart-center") return "Leipzig expert rhythm window";
  return source ? source.replaceAll("_", " ") : "Loading source";
}

function subskillMasteryFor(profile: LearnerProfile | null, concept: string, subskill: LearningSubskill): number {
  return profile?.subskillMastery.find((row) => row.concept === concept && row.subskill === subskill)?.independentMastery
    ?? 0.15;
}

const MEASUREMENT_CLASSIFICATION_TARGETS = new Set(["rate", "qrs_duration", "qt_interval"]);

function classificationContract(concept: string) {
  if (concept === "rate") {
    return {
      prompt: "Classify the ventricular rate band from the tracing.",
      presentLabel: "Within 60–100 bpm",
      absentLabel: "Outside 60–100 bpm",
    };
  }
  if (concept === "qrs_duration") {
    return {
      prompt: "Is the measured QRS wide at the adult 120 ms threshold?",
      presentLabel: "Wide (≥120 ms)",
      absentLabel: "Not wide (<120 ms)",
    };
  }
  if (concept === "qt_interval") {
    return {
      prompt: "Is the packet-grounded QTc at least 480 ms?",
      presentLabel: "QTc ≥480 ms",
      absentLabel: "QTc <480 ms",
    };
  }
  return {
    prompt: `Does this tracing support ${conceptLabel(concept)}?`,
    presentLabel: "Target present",
    absentLabel: "Target absent",
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
    return (leftReceipt?.independentMastery ?? 0.15) - (rightReceipt?.independentMastery ?? 0.15)
      || (rightReceipt?.highConfidenceWrong ?? 0) - (leftReceipt?.highConfidenceWrong ?? 0)
      || (leftReceipt?.independentAttempts ?? 0) - (rightReceipt?.independentAttempts ?? 0)
      || Number(highYield.has(right.id)) - Number(highYield.has(left.id))
      || right.reliableCaseCount - left.reliableCaseCount;
  })[0]?.id ?? chooseDefaultConcept(catalog, groups);
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

function measurementExpectedMs(concept: string, packet: CasePacket | null): number | null {
  if (!packet) return null;
  const measurements = packet.ptbxl_plus.measurements;
  const numeric = (key: string) => typeof measurements[key] === "number" ? measurements[key] as number : null;
  if (concept === "rate") {
    const rate = numeric("heart_rate");
    return rate && rate > 0 ? 60_000 / rate : null;
  }
  if (concept.includes("qt")) return numeric("qt_ms");
  if (concept.includes("av_block") || concept.startsWith("pr_")) return numeric("pr_ms");
  if (concept.includes("qrs") || concept.includes("bundle") || concept.includes("conduction")) return numeric("qrs_ms");
  return null;
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
  const [groups, setGroups] = useState<ConceptGroup[]>([]);
  const [catalog, setCatalog] = useState<CatalogConcept[]>([]);
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [trainingTarget, setTrainingTarget] = useState("");
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState("");
  const [handoffConcept, setHandoffConcept] = useState("");
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [campaignPayload, setCampaignPayload] = useState<TrainingCampaignPayload | null>(null);
  const [campaignLength, setCampaignLength] = useState<number>(10);
  const [poolInfo, setPoolInfo] = useState<TrainingPoolInfo | null>(null);
  const [poolLoading, setPoolLoading] = useState(false);
  const [sessionIndex, setSessionIndex] = useState(0);
  const [sessionComplete, setSessionComplete] = useState(false);

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
        const params = new URLSearchParams(window.location.search);
        const requestedConcept = params.get("concept") ?? "";
        const requestedFocus = params.get("focus") ?? "";
        const requestedTarget = requestedFocus || requestedConcept;
        const requestedSubskill = params.get("subskill") ?? "";
        const requestedReturn = params.get("returnTo") ?? "";
        const isGuidedHandoff = Boolean(requestedFocus && requestedReturn.startsWith("/learn/"));
        if (requestedReturn.startsWith("/learn/") || ["/rapid", "/practice", "/review"].includes(requestedReturn)) {
          setReturnTo(requestedReturn);
        }
        const initialSubskill = isLearningSubskill(requestedSubskill) ? requestedSubskill : "recognize";
        setTrainingSubskill(initialSubskill);

        if (activeCampaign.campaign) {
          const resumed = activeCampaign.campaign;
          const resumedContext = new URLSearchParams(resumed.contextKey);
          const receiptConcept = resumedContext.get("receiptConcept") || resumed.conceptId;
          const resumedReturn = resumedContext.get("returnTo") || requestedReturn;
          setTrainingTarget(resumed.conceptId);
          if (isLearningSubskill(resumed.subskill)) setTrainingSubskill(resumed.subskill);
          setCampaignLength(resumed.requestedLength);
          setAdaptiveMode(resumedContext.get("adaptive") === "true");
          if (receiptConcept !== resumed.conceptId) {
            setHandoffConcept(receiptConcept);
            setHandoffResolution({
              requestedConcept: receiptConcept,
              caseConcept: resumed.conceptId,
              exact: false,
              rationale: "the campaign preserves the lesson's validated proxy target",
            });
          }
          if (resumedReturn.startsWith("/learn/") || ["/rapid", "/practice", "/review"].includes(resumedReturn)) {
            setReturnTo(resumedReturn);
          }
          applyCampaignPayload(activeCampaign, receiptConcept);
          setSelectionReason("Resumed your server-owned campaign at the exact saved case and phase. No ECG was re-selected in the browser.");
          return;
        }

        const availableIds = availableConcepts(conceptData.practiceGroups).map((concept) => concept.id);
        const resolution = requestedTarget ? resolveHandoffTarget(requestedTarget, availableIds) : null;
        if (requestedTarget && !resolution) {
          setAdaptiveMode(!isGuidedHandoff);
          setHandoffConcept(isGuidedHandoff ? requestedTarget : "");
          setTrainingTarget("");
          setEmptyReason(isGuidedHandoff
            ? `No validated case family can currently prove ${requestedTarget.replaceAll("_", " ")} in Competency Lab. Return to the lesson or choose a different competency; no substitute attempt will be recorded.`
            : `No validated case family is available for ${requestedTarget.replaceAll("_", " ")}. Choose another competency; no substitute attempt will be recorded.`);
          return;
        }
        setHandoffConcept(isGuidedHandoff ? resolution?.requestedConcept ?? "" : "");
        setHandoffResolution(isGuidedHandoff ? resolution : null);
        setAdaptiveMode(!requestedTarget);
        const initialTarget = resolution?.caseConcept
          ?? chooseAdaptiveTarget(conceptData.concepts, conceptData.practiceGroups, learnerData, initialSubskill);
        setTrainingTarget(initialTarget);
        if (!initialTarget) {
          setEmptyReason("No concept currently has enough reliable Tier A/B cases for competency training.");
        } else {
          setEmptyReason("Choose a campaign length, then start when you are ready.");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Training could not be loaded.");
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
  }, []);

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
          setEmptyReason("No distinct audited Tier A/B waveform ECGs currently satisfy this concept and subskill contract.");
        } else {
          setEmptyReason("Choose a campaign length, then start when you are ready.");
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "The eligible ECG pool could not be counted.");
      })
      .finally(() => {
        if (!cancelled) setPoolLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [campaignPayload?.campaign, trainingSubskill, trainingTarget]);

  const activeGroup = useMemo(
    () => groups.find((group) => group.concepts.some((concept) => concept.id === trainingTarget)) ?? null,
    [groups, trainingTarget],
  );
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
  const targetIsHighYield = catalog.some((concept) => concept.id === trainingTarget && concept.highYield);
  const evidenceConcept = handoffConcept || trainingTarget;
  const classificationTarget = trainingTarget;
  const answerContract = classificationContract(classificationTarget);
  const targetMastery = subskillMasteryFor(profile, evidenceConcept, trainingSubskill);
  const focusConfidence = evidenceConcept ? packet?.concept_confidence?.[evidenceConcept] : undefined;
  const teachingPoints = result ? asStringArray(result.grade.teachingPoints) : [];
  const selectedAnswerLabel = selectedAnswer === "present" ? answerContract.presentLabel
    : selectedAnswer === "absent" ? answerContract.absentLabel
      : "No decision";
  const groundedAnswerLabel = classificationTruth === "present" ? answerContract.presentLabel
    : classificationTruth === "absent" ? answerContract.absentLabel
      : "Ground truth unavailable";
  const waveformRois = packet?.ptbxl_plus.fiducials.rois ?? [];
  const viewerTask = taskForTraining(trainingSubskill, evidenceConcept);
  const subskillTask = campaignPayload?.current?.task ?? null;
  const activeSubskillLabel = TRAINING_SUBSKILLS.find((item) => item.id === trainingSubskill)?.label ?? trainingSubskill;
  const campaign = campaignPayload?.campaign ?? null;
  const campaignSummary: TrainingCampaignSummary | null = campaignPayload?.summary ?? null;
  const currentSlot = campaignPayload?.current?.slot ?? null;
  const activePhase = currentSlot?.phase
    ?? "target";
  const activeRecipe = PHASE_META[activePhase];
  const sessionCorrect = campaignSummary?.correct ?? 0;
  const transferAttemptCount = campaignSummary?.byPhase.transfer.attempted ?? 0;
  const transferCorrect = campaignSummary?.byPhase.transfer.correct ?? 0;
  const independentReceipts = campaignSummary?.independentReceipts ?? 0;
  const committedCount = campaignSummary?.attempted ?? 0;
  const campaignTotal = campaign?.length ?? 0;
  const readyForRapid = campaignTotal > 0
    && sessionCorrect / campaignTotal >= 0.8
    && transferAttemptCount > 0
    && transferCorrect / transferAttemptCount >= 2 / 3;
  const suggestedAdaptiveTarget = chooseAdaptiveTarget(catalog, groups, profile, trainingSubskill);
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
    setSessionIndex(0);
    setSessionComplete(false);
    setSelectionReason("");
    setEmptyReason(message);
  }

  function applyCampaignPayload(next: TrainingCampaignPayload, receiptConceptOverride?: string) {
    setCampaignPayload(next);
    const nextCampaign = next.campaign;
    if (!nextCampaign) {
      clearWorkspace("Choose a campaign length, then start when you are ready.");
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
        ? "Campaign complete. Your immutable case ledger and evidence summary are saved."
        : "The server is preparing the next unique ECG in this campaign.");
      return;
    }

    setSessionIndex(current.slot.position);
    setCaseFocus(current.slot.caseFocus ?? "");
    setCaseSummary(current.case);
    setPacket(current.packet);
    setEmptyReason(null);
    setSelectionReason(
      `Server-owned slot ${current.slot.position + 1} of ${nextCampaign.length}: one distinct ${sourceLabel(current.packet.source)} ECG, fixed to the immutable ${current.slot.phase} phase.`,
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
    setConfidence(response.confidence);
    setHintsUsed(response.hintsUsed);
    setViewerTaskEvidence(response.viewerTaskEvidence ?? null);
    setHintText(response.hintsUsed ? "A visual hint was used before this response was committed." : "");
    setSubskillReceipt(answer.receipt.effectiveEvidenceLevel === "independent_transfer"
      ? `${conceptLabel(receiptConceptOverride || handoffConcept || nextCampaign.conceptId)} · ${nextCampaign.subskill.replaceAll("_", " ")} recorded as an exact server-graded independent transfer ${answer.summary.correct ? "success" : "miss"}.`
      : `${conceptLabel(receiptConceptOverride || handoffConcept || nextCampaign.conceptId)} · ${nextCampaign.subskill.replaceAll("_", " ")} saved as formative evidence.`);
    setResult({
      correct: answer.summary.correct,
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

  async function startCampaign(replaceActive = false) {
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
      applyCampaignPayload(next, evidenceConcept);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The Training campaign could not be started.");
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
      setCampaignPayload(null);
      clearWorkspace("Campaign abandoned. Choose a competency and length to start a new immutable case ledger.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The Training campaign could not be abandoned.");
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
      setHandoffConcept("");
      setHandoffResolution(null);
      setAdaptiveMode(true);
      setTrainingTarget(suggestedAdaptiveTarget);
      clearWorkspace("Counting distinct eligible ECGs for the next weakest competency…");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The next adaptive competency could not be prepared.");
    } finally {
      setLoading(false);
    }
  }

  function resetCurrentSet() {
    void startCampaign(Boolean(campaign));
  }

  function changeTarget(value: string) {
    if (campaign) return;
    clearWorkspace("Counting distinct source-contracted waveform ECGs for this competency…");
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
      setError(err instanceof Error ? err.message : "The next saved Training case could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  function enableAdaptiveMode() {
    if (campaign) return;
    const target = chooseAdaptiveTarget(catalog, groups, profile, trainingSubskill);
    clearWorkspace("Counting the eligible ECG pool for your weakest competency…");
    setAdaptiveMode(true);
    setHandoffConcept("");
    setHandoffResolution(null);
    setTrainingTarget(target);
  }

  function subskillEvidenceIsValid(evidence = viewerTaskEvidence, evidencePacket = packet) {
    if (trainingSubskill === "recognize" || trainingSubskill === "calibrate_confidence") return true;
    if (trainingSubskill === "localize") {
      const pointValid = evidence?.mode === "point" && evidence.correct === true;
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
      if (evidence?.mode !== "caliper" || evidence.correct === false || evidence.noTarget) return false;
      const expected = measurementExpectedMs(evidenceConcept, evidencePacket);
      if (expected === null) return false;
      const tolerance = evidenceConcept === "rate" ? 90 : 35;
      return Math.abs(evidence.valueMs - expected) <= tolerance;
    }
    if (["discriminate", "explain_mechanism"].includes(trainingSubskill)) {
      return subskillTask?.kind === "single_choice" && Boolean(subskillTaskAnswer);
    }
    return evidenceNote.trim().length >= 20;
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
        receiptConcept: evidenceConcept,
      });
      applyCampaignPayload(next, evidenceConcept);
      try {
        setProfile(await api.profile());
      } catch {
        // The durable answer and receipt already succeeded; profile refresh can wait for reload.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Your answer could not be submitted.");
    } finally {
      setLoading(false);
    }
  }

  if (booting) {
    return (
      <div className="page train-page">
        <div className="panel pad train-loading">Loading the competency map and a grounded case...</div>
      </div>
    );
  }

  return (
    <div className="page train-page">
      <header className="page-header train-header">
        <div>
          <p className="eyebrow">Mode 2 · Competency training</p>
          <h1>Train one visual skill until it sticks</h1>
          <p className="muted">
            Contrast real ECGs with nearby mimics, commit a target-present/target-absent decision, then study the grounded evidence and ask the tutor why.
          </p>
        </div>
        <div className="actions train-header-actions">
          {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} aria-hidden="true" /> Return to lesson</Link> : null}
          {campaign ? (
            <button className="button warn" type="button" onClick={() => void abandonCurrentCampaign()} disabled={loading}>
              <XCircle size={16} aria-hidden="true" /> Abandon campaign
            </button>
          ) : null}
        </div>
      </header>

      {returnTo ? (
        <div className="selection-note" style={{ marginBottom: 14 }}>
          This set was launched for <strong>{evidenceConcept.replaceAll("_", " ")} · {trainingSubskill.replaceAll("_", " ")}</strong>. Your lesson state is preserved.
          {handoffResolution && !handoffResolution.exact ? <> It uses the validated <strong>{conceptLabel(handoffResolution.caseConcept)}</strong> case family because {handoffResolution.rationale}; the requested subskill gate below must still be completed.</> : null}
        </div>
      ) : null}

      {error ? <div className="warning train-error">{error}</div> : null}

      {!campaign ? (
        <section className="panel pad train-campaign-setup" aria-label="Configure Training campaign">
          <div>
            <p className="eyebrow">Durable real-ECG campaign</p>
            <h2>Choose how far you want to train</h2>
            <p className="muted">
              Every ECG is selected once on the server, persisted to your account, and never repeated inside this campaign. Your request is capped honestly by the distinct eligible pool for this exact concept and subskill.
            </p>
          </div>
          <div className="train-campaign-controls">
            <div className="field">
              <label htmlFor="train-campaign-length">Requested unique ECGs</label>
              <select
                id="train-campaign-length"
                value={campaignLength}
                onChange={(event) => setCampaignLength(Number(event.target.value))}
                disabled={loading}
              >
                {CAMPAIGN_LENGTHS.map((length) => <option value={length} key={length}>{length.toLocaleString()}</option>)}
              </select>
            </div>
            <div className="train-pool-readout" aria-live="polite">
              <strong>{poolLoading ? "Counting…" : `${(poolInfo?.eligibleDistinct ?? 0).toLocaleString()} distinct eligible`}</strong>
              <span className="muted">Audited Tier A/B waveform ECGs only</span>
              {!poolLoading && poolInfo ? <span className="muted">
                {poolInfo.roleCounts.target.toLocaleString()} target-positive · {poolInfo.roleCounts.mimic.toLocaleString()} close-mimic · {poolInfo.roleCounts.negative.toLocaleString()} other negative
              </span> : null}
              {!poolLoading && poolInfo && campaignLength > poolInfo.eligibleDistinct ? (
                <span className="uncertainty">Your {campaignLength.toLocaleString()} request will be capped at {poolInfo.eligibleDistinct.toLocaleString()}; no synthetic or repeated case will fill the gap.</span>
              ) : null}
            </div>
            {!poolLoading && poolInfo?.eligibleDistinct === 0 ? (
              <p className="warning train-empty-reason" role="status">
                {emptyReason ?? "This exact concept and subskill do not currently have an eligible real-ECG pool."} Choose another subskill or concept to continue.
              </p>
            ) : null}
            <button
              className="button primary"
              type="button"
              onClick={() => void startCampaign()}
              disabled={loading || poolLoading || !trainingTarget || !poolInfo?.eligibleDistinct}
            >
              <ShieldCheck size={16} aria-hidden="true" /> Start immutable campaign
            </button>
          </div>
        </section>
      ) : (
        <>
          <section className="selection-note train-selection-note" style={{ marginBottom: 16 }}>
            <div className="case-label"><Sparkles size={16} aria-hidden="true" /> Server-owned, mastery-aware contrast campaign</div>
            <p className="muted" style={{ margin: "6px 0 0" }}>{selectionReason}</p>
            <div className="pill-row" style={{ marginTop: 10 }}>
              <span className="pill">{campaign.length.toLocaleString()} unique ECGs planned</span>
              <span className="pill">{campaign.poolCount.toLocaleString()} eligible at creation</span>
              <span className="pill">{campaign.status === "complete" ? "Complete" : "Resume-safe"}</span>
              <span className="pill">Source-contract eligible</span>
            </div>
            {campaign.length < campaign.requestedLength ? (
              <p className="uncertainty" style={{ margin: "10px 0 0" }}>
                Requested {campaign.requestedLength.toLocaleString()}; capped at the {campaign.length.toLocaleString()} distinct eligible ECGs available when this campaign was created.
              </p>
            ) : null}
          </section>

          <section className="panel pad train-session-panel" aria-label="Focused training campaign">
            <div className="train-session-heading">
              <div>
                <p className="eyebrow">
                  Focused campaign · {currentSlot ? `Case ${currentSlot.position + 1}` : `${committedCount} cases`} of {campaign.length.toLocaleString()}
                </p>
                <h2>{activeRecipe.label}</h2>
                <p className="muted">{activeRecipe.purpose}. Early exposures are labeled practice. In transfer, only an exact server-graded localization, measurement, contrast, mechanism, or confidence task can earn an independent receipt; every other response remains formative.</p>
              </div>
              <strong>{committedCount.toLocaleString()}/{campaign.length.toLocaleString()} committed</strong>
            </div>
            <div className="train-session-progress" aria-label={`${committedCount} of ${campaign.length} cases committed`}>
              <span style={{ width: `${Math.round((committedCount / Math.max(1, campaign.length)) * 100)}%` }} />
            </div>
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
          </section>
        </>
      )}

      <div className="grid two viewer-hero train-workspace">
        <main className="grid train-viewer-column">
          {caseSummary ? (
            <ECGViewer
              caseId={caseSummary.caseId}
              actions={viewerActions}
              groundedRois={result ? waveformRois : []}
              gradingRois={waveformRois}
              onCoordinate={setSelectedPoint}
              medianBeats={packet?.ptbxl_plus.median_beats ?? null}
              task={!result ? viewerTask : undefined}
              onTaskEvidence={setViewerTaskEvidence}
            />
          ) : (
            <div className="panel pad train-empty">{emptyReason ?? "Loading a confidence-gated ECG..."}</div>
          )}

          {packet ? (
            <section className="panel pad train-provenance" aria-label="ECG provenance">
              <h2><Database size={18} aria-hidden="true" /> Recording provenance</h2>
              <div className="pill-row">
                <span className="pill">Record {packet.display_id || caseSummary?.displayId}</span>
                <span className="pill">{sourceLabel(packet.source)}</span>
                <span className="pill">Teaching Tier {packet.teaching_tier}</span>
                <span className="pill">Signal {packet.signal_quality.status}</span>
                <span className="pill">{packet.waveform.sampling_frequency} Hz · {packet.waveform.duration_sec}s</span>
              </div>
              {packet.source === "fixture" ? (
                <p className="warning train-fixture-warning" style={{ marginTop: 12, marginBottom: 0 }}>
                  This source does not satisfy the campaign contract and should not be used for competency evidence.
                </p>
              ) : (
                <p className="selection-note train-real-data-note" style={{ marginTop: 12, marginBottom: 0 }}>
                  <ShieldCheck size={15} aria-hidden="true" /> Real waveform data. Labels, reports, concept scores, and diagnostic statements remain blinded until you commit.
                </p>
              )}
              {selectedPoint ? (
                <p className="status-line train-coordinate" style={{ marginTop: 12, marginBottom: 0 }}>
                  Cursor: {selectedPoint.lead} · {selectedPoint.timeSec.toFixed(3)} s · {selectedPoint.amplitudeMv.toFixed(3)} mV
                </p>
              ) : null}
            </section>
          ) : null}

          {result && packet ? (
            <section className="panel pad train-evidence" aria-label="Grounded case evidence">
              <h2><Eye size={18} aria-hidden="true" /> Grounded reveal</h2>
              <div className="evidence-grid train-evidence-grid">
                <div className="evidence-card train-confidence-card">
                  <h3>{conceptLabel(evidenceConcept)} · {groundedAnswerLabel}</h3>
                  {focusConfidence ? (
                    <>
                      <p className="muted">Tier {focusConfidence.tier} · {Math.round(focusConfidence.score * 100)}% concept confidence</p>
                      <div className="compact-list">
                        {focusConfidence.evidence.map((item) => <p className="muted" key={item}>{item.replaceAll("_", " ")}</p>)}
                      </div>
                    </>
                  ) : (
                    <p className="muted">
                      {classificationTruth === "absent"
                        ? `The grounded packet does not support ${conceptLabel(classificationTarget)}. The contrast case is ${conceptLabel(caseFocus)}.`
                        : "No concept-confidence row was supplied for this exact competency; the binary decision is grounded by the packet contract above."}
                    </p>
                  )}
                </div>
                <div className="evidence-card train-source-evidence">
                  <h3>Independent source evidence</h3>
                  <div className="compact-list">
                    {(packet.ptbxl_plus.statements ?? []).slice(0, 3).map((statement) => (
                      <p className="muted" key={statement}>{statement}</p>
                    ))}
                    {packet.ptbxl?.report ? <p className="muted">Source report or expert annotation: {packet.ptbxl.report}</p> : null}
                    {!packet.ptbxl_plus.statements?.length && !packet.ptbxl?.report ? (
                      <p className="muted">No report-level evidence was supplied; use the confidence evidence and teaching points.</p>
                    ) : null}
                  </div>
                </div>
              </div>
              {focusConfidence?.warnings.length ? (
                <p className="uncertainty train-confidence-warning" style={{ marginTop: 12 }}>
                  {focusConfidence.warnings.join(" ")}
                </p>
              ) : null}
            </section>
          ) : null}
        </main>

        <aside className="lesson-rail train-rail">
          <section className="panel pad train-target-panel">
            <h2><Target size={18} aria-hidden="true" /> {campaign ? "Campaign competency" : "Choose a competency"}</h2>
            <div className="field train-target-field">
              <label htmlFor="train-target">Target concept</label>
              <select
                id="train-target"
                value={trainingTarget}
                onChange={(event) => changeTarget(event.target.value)}
                disabled={loading || Boolean(handoffConcept) || Boolean(campaign)}
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
            <button className={`button small ${adaptiveMode ? "primary" : "subtle"}`} style={{ marginTop: 10 }} type="button" aria-pressed={adaptiveMode} onClick={enableAdaptiveMode} disabled={loading || Boolean(campaign)}>
              <Sparkles size={15} aria-hidden="true" /> {adaptiveMode ? "Adaptive targeting · weakest competency" : "Use weakest-competency plan"}
            </button>
            <div className="field train-target-field" style={{ marginTop: 10 }}>
              <label htmlFor="train-subskill">Target subskill</label>
              <select id="train-subskill" value={trainingSubskill} onChange={(event) => changeSubskill(event.target.value)} disabled={loading || Boolean(handoffConcept) || Boolean(campaign)}>
                {TRAINING_SUBSKILLS.map((subskill) => <option key={subskill.id} value={subskill.id}>{subskill.label}</option>)}
              </select>
            </div>
            {handoffConcept ? (
              <p className="selection-note" style={{ marginTop: 10 }}>
                This lesson target is locked so its competency receipt cannot drift. {campaign ? "Abandon this campaign before changing its target." : <>Choose <strong>Use weakest-competency plan</strong> to release the handoff and start a separate adaptive campaign.</>}
              </p>
            ) : null}
            <div className="objective-meta train-mastery-meta" style={{ marginTop: 14 }}>
              <strong>{conceptLabel(evidenceConcept)}</strong>
              <span className="muted">{trainingSubskill.replaceAll("_", " ")} · {Math.round(targetMastery * 100)}%</span>
            </div>
            {targetIsHighYield ? <span className="pill train-high-yield" style={{ marginTop: 10 }}>High-yield target</span> : null}
            <div className={`mastery-bar ${masteryClass(targetMastery)} train-mastery-bar`} aria-label={`${Math.round(targetMastery * 100)} percent mastery`}>
              <span style={{ width: `${Math.round(targetMastery * 100)}%` }} />
            </div>
            <p className="muted" style={{ margin: "10px 0 0" }}>
              {activeGroup?.label ?? "Concept family"} · {activeGroup?.availableConceptCount ?? 0} reliable concepts. The receipt below is always for <strong>{conceptLabel(evidenceConcept)} · {trainingSubskill.replaceAll("_", " ")}</strong>.
            </p>
            {handoffResolution && !handoffResolution.exact ? (
              <p className="selection-note" style={{ marginTop: 10 }}>
                Formative proxy tracing: the decision asks about <strong>{conceptLabel(classificationTarget)}</strong>; it cannot create independent {conceptLabel(evidenceConcept)} mastery.
              </p>
            ) : null}
          </section>

          {campaign && packet ? (
          <section className="panel pad train-drill-panel">
            <h2>{activeSubskillLabel}</h2>
            <p className="muted">
              <strong>{conceptLabel(classificationTarget)}:</strong> {answerContract.prompt} Choose one mutually exclusive answer after reading the trace.
            </p>
            {viewerTask ? <p className="selection-note"><strong>Structured waveform {viewerTask.mode} task:</strong> {viewerTask.prompt} This response is checked against packet coordinates or measurements, not inferred from your classification.</p> : null}
            <div className="grid train-options" role="group" aria-label="Target decision">
              {([
                { id: "present" as const, label: answerContract.presentLabel },
                { id: "absent" as const, label: answerContract.absentLabel },
              ]).map((option) => {
                const selected = option.id === selectedAnswer;
                return (
                  <button
                    className={`button ${selected ? "primary" : "subtle"} train-option`}
                    style={{ width: "100%", justifyContent: "flex-start", textAlign: "left" }}
                    type="button"
                    key={option.id}
                    aria-pressed={selected}
                    onClick={() => setSelectedAnswer(option.id)}
                    disabled={Boolean(result) || loading}
                  >
                    {selected ? <CheckCircle2 size={16} aria-hidden="true" /> : <Target size={16} aria-hidden="true" />}
                    {option.label}
                  </button>
                );
              })}
            </div>

            {subskillTask ? (
              <div className="panel pad train-subskill-task" style={{ marginTop: 14 }}>
                <p className="eyebrow">Exact {subskillTask.subskill.replaceAll("_", " ")} task</p>
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
                          disabled={Boolean(result) || loading}
                        >
                          {selected ? <CheckCircle2 size={15} aria-hidden="true" /> : <Target size={15} aria-hidden="true" />}
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="selection-note"><strong>Scoring rule:</strong> your pre-feedback confidence is compared with whether the blinded target decision is correct. One result is an observation, not proof of durable calibration.</p>
                )}
                <p className="muted" style={{ marginBottom: 0 }}>{subskillTask.gradingBoundary}</p>
              </div>
            ) : null}

            <div className="field train-evidence-field" style={{ marginTop: 14 }}>
              <label htmlFor="train-evidence-note">Evidence statement <span className="muted">{["synthesize", "apply_in_context"].includes(trainingSubskill) || (trainingSubskill === "measure" && !viewerTask) || (trainingSubskill === "localize" && (evidenceConcept.includes("lead_territor") || evidenceConcept.includes("frontal_lead_map"))) ? "(required)" : "(recommended)"}</span></label>
              <textarea
                id="train-evidence-note"
                value={evidenceNote}
                onChange={(event) => setEvidenceNote(event.target.value)}
                placeholder="Example: QRS is wide, then compare the terminal direction in V1 and V6."
                disabled={Boolean(result) || loading}
              />
            </div>

            <div className="field train-confidence-field" style={{ marginTop: 12 }}>
              <label htmlFor="train-confidence">Confidence</label>
              <select
                id="train-confidence"
                value={confidence}
                onChange={(event) => setConfidence(Number(event.target.value))}
                disabled={Boolean(result) || loading}
              >
                <option value={1}>1 · Guessing</option>
                <option value={2}>2 · Unsure</option>
                <option value={3}>3 · Moderate</option>
                <option value={4}>4 · Confident</option>
                <option value={5}>5 · Very confident</option>
              </select>
            </div>

            {!result ? (
              <div className="actions train-drill-actions" style={{ marginTop: 14 }}>
                <button className="button warn train-hint-button" type="button" onClick={requestHint} disabled={!packet || hintsUsed > 0 || loading}>
                  <Lightbulb size={16} aria-hidden="true" />
                  {hintsUsed ? "Hint used" : "Show one visual hint"}
                </button>
                <button className="button primary train-commit-button" type="button" onClick={() => void commitAnswer()} disabled={!selectedAnswer || !subskillEvidenceIsValid() || loading}>
                  <Send size={16} aria-hidden="true" />
                  Commit target decision
                </button>
              </div>
            ) : null}
            {hintText ? <p className="uncertainty train-hint-text" style={{ marginTop: 12, marginBottom: 0 }}>{hintText}</p> : null}
          </section>
          ) : (
            <section className="panel pad train-tutor-lock">
              <h2><ShieldCheck size={18} aria-hidden="true" /> Campaign not started</h2>
              <p className="muted" style={{ marginBottom: 0 }}>
                Select the competency here, then choose a length in the campaign panel above. The first blinded ECG appears only after the server has persisted the full unique-case ledger.
              </p>
            </section>
          )}

          {campaign ? result ? (
            <section className="panel pad train-feedback-panel" aria-live="polite">
              <h2>
                {result.correct ? <CheckCircle2 size={18} aria-hidden="true" /> : <XCircle size={18} aria-hidden="true" />}
                {result.correct ? "Contrast caught" : "Re-check the discriminator"}
              </h2>
              <div className="feedback-score train-feedback-score">
                <strong>{result.correct ? "Correct" : "Not yet"}</strong>
                <span className="muted">Grounded {conceptLabel(classificationTarget)} answer: {groundedAnswerLabel}</span>
              </div>
              <p>
                You chose <strong>{selectedAnswerLabel}</strong>. {result.correct
                  ? "Your target decision and required subskill evidence agree with the reviewed packet."
                  : `Re-check the evidence for ${conceptLabel(classificationTarget)} before carrying this pattern forward.`}
              </p>
              {!result.focusGrounded ? (
                <p className="warning train-grounding-mismatch">
                  The post-commit packet could not verify this target-decision contract, so this attempt remains formative and should not be treated as an independent example.
                </p>
              ) : null}
              {subskillReceipt ? <p className="selection-note train-mastery-delta">{subskillReceipt}</p> : null}
              <div className="pill-row train-feedback-tags">
                <span className={`pill ${result.correct ? "" : "disabled"}`}>{conceptLabel(evidenceConcept)} · {trainingSubskill.replaceAll("_", " ")}</span>
                {classificationTruth === "absent" ? <span className="pill">Contrast finding: {conceptLabel(caseFocus)}</span> : null}
              </div>
              {teachingPoints.length ? (
                <div className="compact-list train-teaching-points" style={{ marginTop: 14 }}>
                  <h3>Teaching points</h3>
                  {teachingPoints.slice(0, 4).map((point) => <p className="muted" key={point}>{point}</p>)}
                </div>
              ) : null}
              {!sessionComplete ? (
                <button className="button primary train-next-button" style={{ marginTop: 14 }} type="button" onClick={loadNextAdaptiveDrill} disabled={loading}>
                  Next case in set <ArrowRight size={16} aria-hidden="true" />
                </button>
              ) : null}
            </section>
          ) : (
            <section className="panel pad train-tutor-lock">
              <h2><Brain size={18} aria-hidden="true" /> Tutor on the back burner</h2>
              <p className="muted" style={{ marginBottom: 0 }}>
                Commit first so the grounded answer stays hidden. Afterward, the tutor can explain the discriminator, answer tangents, and control the viewer.
              </p>
            </section>
          ) : null}

          {sessionComplete && campaign ? (
            <section className="panel pad train-debrief-panel" aria-live="polite">
              <p className="eyebrow">Campaign complete · durable evidence debrief</p>
              <h2>{sessionCorrect.toLocaleString()}/{campaign.length.toLocaleString()} competency gates met</h2>
              <p className="muted">
                A gate requires the target decision and the selected {trainingSubskill.replaceAll("_", " ")} evidence. Build, mimic, negative, and unsupported responses remain formative; {independentReceipts} exact server-graded transfer receipt{independentReceipts === 1 ? "" : "s"} cleared the evidence ceiling.
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
                <strong><Sparkles size={15} aria-hidden="true" /> Adaptive next-step recommendation</strong>
                {readyForRapid ? (
                  <p>Your transfer held on {transferCorrect}/{transferAttemptCount} unannounced cases with at least 80% accuracy overall. Move to a mixed Rapid round so the target is no longer named in advance.</p>
                ) : (
                  <p>Repeat this focused competency. A new server-owned ledger will again keep target, mimic, negative, and transfer performance separate.</p>
                )}
              </div>
              <div className="actions train-debrief-actions">
                <button className="button primary" type="button" onClick={resetCurrentSet} disabled={loading}>
                  <RefreshCw size={16} aria-hidden="true" /> Start another campaign
                </button>
                {readyForRapid ? (
                  <Link className="button" href={`/rapid?focus=${encodeURIComponent(evidenceConcept)}&subskill=synthesize`}>
                    Start mixed Rapid <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                ) : null}
                {!handoffConcept && suggestedAdaptiveTarget && suggestedAdaptiveTarget !== trainingTarget ? (
                  <button className="button subtle" type="button" onClick={() => void prepareNextWeakConcept()} disabled={loading}>
                    Train next weak concept
                  </button>
                ) : null}
                {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} aria-hidden="true" /> Return to lesson</Link> : null}
              </div>
            </section>
          ) : null}

          {result && caseSummary ? (
            <TutorChat
              mode="practice"
              roleLabel="Coach · post-commit"
              caseId={caseSummary.caseId}
              viewerState={viewerState}
              onViewerActions={setViewerActions}
              openingPrompt={`Ask why ${conceptLabel(classificationTarget)} was ${classificationTruth === "present" ? "present" : "absent"}, how ${conceptLabel(caseFocus)} changes the contrast, or ask me to highlight the decisive feature.`}
              resetKey={caseSummary.caseId}
            />
          ) : null}
        </aside>
      </div>
    </div>
  );
}
