export type Tier = "A" | "B" | "C" | "D";

export type ConceptConfidence = {
  score: number;
  tier: Tier;
  evidence: string[];
  warnings: string[];
};

export type CaseSummary = {
  caseId: string;
  displayId: string;
  source: string;
  teachingTier: Tier;
  clinicalStem: string;
  topConcepts: Array<{ id: string; score: number; tier: Tier; evidence: string[]; warnings: string[] }>;
  report: string;
  studentFacing: boolean;
};

export type ViewerAction = {
  type: "zoom" | "highlightLead" | "highlightROI" | "circleROI" | "drawCaliper" | "showFiducial" | "resetView";
  leads?: string[];
  lead?: string;
  timeStart?: number;
  timeEnd?: number;
  ampMin?: number;
  ampMax?: number;
  timeSec?: number;
  label?: string;
};

export type ViewerTaskSpec =
  | { mode: "point"; prompt: string; concept: string; allowedLeads?: string[] }
  | { mode: "region"; prompt: string; concept: string; allowedLeads?: string[]; minimumDurationMs?: number }
  | { mode: "caliper"; prompt: string; measurement: "rr" | "pr" | "qrs" | "qt" | "custom"; allowedLeads?: string[] }
  | { mode: "march"; prompt: string; target: "p_waves" | "qrs_complexes" | "rr_intervals"; minimumMarkers: number; allowedLeads?: string[] };

export type ViewerTaskEvidence =
  | { mode: "point"; point: import("@/lib/coordinates").ECGPoint; correct?: boolean; noTarget?: boolean; feedback?: string }
  | { mode: "region"; roi: GroundedRoi; correct?: boolean; noTarget?: boolean; feedback?: string }
  | { mode: "caliper"; lead: string; timeStartSec: number; timeEndSec: number; valueMs: number; correct?: boolean; noTarget?: boolean; feedback?: string }
  | { mode: "march"; points: import("@/lib/coordinates").ECGPoint[] };

/**
 * Clean averaged median beat per lead (~700 ms), already in mV.
 * `available` is false when the packet has no median-beat data.
 */
export type MedianBeats = {
  available: boolean;
  samplingFrequency: number;
  durationMs: number;
  leads: string[];
  beats: Record<string, number[]>;
};

export type CasePacket = {
  case_id: string;
  display_id: string;
  clinical_stem: string;
  source: string;
  /** True for the blinded practice packet (diagnosis-bearing fields are stripped before submission). */
  blinded?: boolean;
  waveform: {
    path: string | null;
    sampling_frequency: number;
    duration_sec: number;
    leads: string[];
    source: string;
  };
  ptbxl_plus: {
    features: Record<string, unknown>;
    fiducials: {
      rois?: GroundedRoi[];
    };
    median_beats: MedianBeats;
    measurements: Record<string, unknown>;
    per_lead_st_mv?: Record<string, unknown>;
    // Diagnosis-bearing; omitted from the blinded packet.
    statements?: string[];
  };
  signal_quality: {
    status: string;
    reasons: string[];
  };
  teaching_tier: Tier;
  inclusion_reasons: string[];
  exclusion_reasons: string[];
  // The fields below carry or reveal the diagnosis; the blinded practice packet omits them.
  ptbxl?: {
    scp_codes: Record<string, number>;
    diagnostic_superclass: string[];
    diagnostic_subclass: string[];
    report: string;
    fold: number;
    metadata: Record<string, unknown>;
  };
  concept_confidence?: Record<string, ConceptConfidence>;
  supported_objectives?: string[];
  unsupported_objectives?: string[];
  llm_allowed_claims?: string[];
  llm_forbidden_claims?: string[];
  teaching_points?: string[];
};

export type RapidRound = {
  roundId: string;
  learnerId: string;
  pace: "ward" | "emergency" | "untimed";
  length: number;
  assessmentScope: "full_read" | "dominant_finding";
  focusConcept: string | null;
  focusSubskill: string | null;
  contextKey: string;
  exclusions: string[];
  servedCount: number;
  recentServed: string[];
  pendingCaseId: string | null;
  feedbackCaseId: string | null;
  pendingStartedAt: string | null;
  pendingDeadlineAt: string | null;
  deadlineSeconds: number | null;
  position: number;
  status: "active" | "complete" | "abandoned";
};

export type RapidEvidenceReceipt = {
  concept: string;
  subskill: string;
  accepted: boolean;
  correct?: boolean;
  evidenceLevel: string;
  reason?: string;
};

export type RapidRoundAnswer = {
  answerId: number;
  roundId: string;
  caseId: string;
  response: Record<string, unknown> & { traceEvidence?: ViewerTaskEvidence | null };
  grade: Record<string, unknown>;
  tutor: TutorResponse | null;
  result: Record<string, unknown>;
  traceGrade: Record<string, unknown> | null;
  receipts: RapidEvidenceReceipt[];
  attemptId: number;
};

export type RapidRoundPayload = {
  round: RapidRound | null;
  current: null | {
    kind: "pending" | "feedback";
    case: CaseSummary;
    packet: CasePacket;
    startedAt?: string | null;
    deadlineAt?: string | null;
    answer?: RapidRoundAnswer;
  };
  results: Array<Record<string, unknown>>;
  resultCount?: number;
  resultsTruncated?: boolean;
  answer?: RapidRoundAnswer;
  receipts?: RapidEvidenceReceipt[];
  replay?: boolean;
  selectionReason?: string;
  targetObjectives?: string[];
};

export type TrainingPhase = "target" | "mimic" | "negative" | "transfer";

export type TrainingCampaign = {
  campaignId: string;
  learnerId: string;
  conceptId: string;
  subskill: string;
  requestedLength: number;
  length: number;
  poolCount: number;
  phaseCounts: Record<TrainingPhase, number>;
  position: number;
  pendingCaseId: string | null;
  feedbackCaseId: string | null;
  status: "active" | "complete" | "abandoned";
  contextKey: string;
  createdAt: string;
  updatedAt: string;
  abandonedAt: string | null;
};

export type TrainingCampaignSlot = {
  position: number;
  phase: TrainingPhase;
  caseId: string;
  caseFocus?: string;
  targetPresent?: boolean;
  status: "queued" | "pending" | "answered";
  servedAt: string | null;
  answeredAt: string | null;
};

export type TrainingCampaignAnswer = {
  answerId: number;
  campaignId: string;
  position: number;
  caseId: string;
  response: {
    selectedAnswer: "present" | "absent";
    confidence: number;
    hintsUsed: number;
    evidenceNote: string;
    viewerTaskEvidence?: ViewerTaskEvidence | null;
    subskillTaskAnswer?: string;
    expectedAnswer: "present" | "absent" | null;
  };
  grade: Record<string, unknown>;
  tutor: TutorResponse | null;
  receipt: {
    requestedEvidenceLevel: string;
    effectiveEvidenceLevel: string;
    receipts?: Array<Record<string, unknown>>;
  };
  summary: {
    position: number;
    caseId: string;
    phase: TrainingPhase;
    correct: boolean;
    classificationCorrect: boolean;
    focusGrounded: boolean;
    selectedResponse: "present" | "absent";
    confidence: number;
    hintsUsed: number;
    evidenceLevel: string;
    misconceptions: string[];
  };
  attemptId: number;
  createdAt: string;
};

export type TrainingCampaignSummary = {
  attempted: number;
  correct: number;
  independentReceipts: number;
  byPhase: Record<TrainingPhase, { attempted: number; correct: number }>;
  recent: TrainingCampaignAnswer["summary"][];
};

export type TrainingCampaignPayload = {
  campaign: TrainingCampaign | null;
  current: null | {
    kind: "pending" | "feedback";
    slot: TrainingCampaignSlot;
    case: CaseSummary;
    packet: CasePacket;
    task?: null | {
      kind: "single_choice" | "confidence_commit";
      subskill: string;
      prompt: string;
      options: Array<{ id: string; label: string }>;
      required: boolean;
      gradingBoundary: string;
    };
    answer?: TrainingCampaignAnswer;
  };
  summary: TrainingCampaignSummary | null;
  answer?: TrainingCampaignAnswer;
  replay?: boolean;
};

export type GroundedRoi = {
  lead: string;
  timeStartSec: number;
  timeEndSec: number;
  ampMinMv: number;
  ampMaxMv: number;
  label: string;
  concept: string;
  source: string;
  confidence: string;
};

export type WaveformResponse = {
  caseId: string;
  samplingFrequency: number;
  durationSec: number;
  startSec: number;
  endSec: number;
  leads: Array<{
    lead: string;
    points: Array<{ timeSec: number; amplitudeMv: number }>;
  }>;
};

export type TutorResponse = {
  tutorMessage: string;
  feedback: string;
  viewerActions: ViewerAction[];
  objectiveUpdates: Array<{ objective: string; delta: number; reason: string }>;
  misconceptions: string[];
  uncertaintyWarnings: string[];
  suggestedNextStep: string;
  socraticQuestion?: string;
  citedEvidence?: string[];
  onLessonTopic?: boolean;
  schemaError?: string | null;
  provider?: string;
  remoteProviderConfigured?: boolean;
  remoteCall?: {
    attempted: boolean;
    status: "not_attempted" | "not_configured" | "request_rejected" | "failed" | "success" | string;
  };
  remoteUsage?: {
    allowed: boolean;
    reason?: "learner_daily" | "ip_hourly" | "global_daily" | null;
    resetAt?: string | null;
    status: "reserved" | "quota_fallback";
    remaining?: Record<string, number>;
    limits?: Record<string, number>;
  };
};

export type TutorMessageResponse = TutorResponse & {
  threadId: string;
};

export type TutorMode = "tutorial" | "practice" | "freeform";

export type TutorThreadMessage = {
  role: "user" | "tutor";
  content: string;
  viewerActions: ViewerAction[];
  meta: {
    socraticQuestion?: string | null;
    onLessonTopic?: boolean;
    citedEvidence?: string[];
  } & Record<string, unknown>;
  createdAt: string;
};

export type TutorThread = {
  threadId: string;
  learnerId?: string;
  mode: TutorMode | string;
  lessonId: string | null;
  caseId: string | null;
  title: string | null;
  createdAt?: string;
  updatedAt?: string;
  messages: TutorThreadMessage[];
};

export type ClickGradeResult = {
  correct: boolean;
  feedback: string;
  matchedRoi: GroundedRoi | null;
  /** True when this case has no grounded target for the requested concept (neutral, not "incorrect"). */
  noTarget?: boolean;
};

export type RegionGradeResult = ClickGradeResult & {
  targetCoverage: number;
  selectionPrecision: number;
};

export type ClickTask = {
  roiConcept: string;
  leads: string[];
  prompt: string;
};

export type ConceptSubskill = {
  id: string;
  label: string;
  reliableCaseCount: number;
  available: boolean;
};

export type ConceptGroup = {
  id: string;
  label: string;
  concepts: ConceptSubskill[];
  reliableCaseCount: number;
  enabled: boolean;
  reason: string;
  availableConceptCount: number;
};

export type LearnerProfile = {
  learnerId: string;
  displayName: string;
  attemptCount: number;
  mastery: Array<{
    objective: string;
    mastery: number;
    attempts: number;
    correct: number;
    highConfidenceWrong: number;
    lastPracticedAt: string | null;
  }>;
  subskillMastery: Array<{
    concept: string;
    subskill: string;
    formativeScore: number;
    independentMastery: number;
    attempts: number;
    independentAttempts: number;
    correct: number;
    highConfidenceWrong: number;
    lastPracticedAt: string | null;
    lastIndependentAt: string | null;
    lastIndependentCorrect: boolean | null;
    nextDueAt: string | null;
    dueState: "unseen" | "scheduled" | "due" | "overdue";
    isDue: boolean;
    overdueDays: number;
    daysUntilDue: number | null;
    stabilityDays: number;
    lapses: number;
    spacedRetrievals: number;
    distinctEligibleEcgs: number;
    distinctSuccessfulEcgs: number;
    distinctModes: number;
    distinctMorphologies: number;
    retentionUncertainty: string | null;
  }>;
  recentAttempts: Array<{
    caseId: string;
    mode: string;
    score: number;
    confidence: number;
    misconceptions: string[];
    createdAt: string;
  }>;
  misconceptions: Array<{ tag: string; count: number }>;
  weakObjectives: string[];
};

export type User = {
  userId: string;
  username: string;
  displayName?: string;
};

export type AuthState = {
  token: string | null;
  user: User | null;
};

export type AuthResponse = {
  token: string;
  user: User;
};

export type MeResponse = {
  authenticated: boolean;
  user: User | null;
};
