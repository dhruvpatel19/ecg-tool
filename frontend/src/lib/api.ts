import type {
  CasePacket,
  CaseSummary,
  ClickGradeResult,
  ClickTask,
  ConceptGroup,
  EcgCapability,
  LearnerProfile,
  MeResponse,
  RegionGradeResult,
  RapidRoundPayload,
  RapidTaskPacket,
  TrainingCampaignPayload,
  TutorMessageResponse,
  TutorResponse,
  TutorThread,
  ViewerAction,
  ViewerTaskEvidence,
  WaveformScope,
  WaveformResponse,
} from "./types";

export type TutorialLesson = {
  id: string;
  title: string;
  objectives: string[];
  caseConcept: string | null;
  steps: string[];
  clickTask: ClickTask | null;
};

export type CurriculumModule = {
  id: string;
  title: string;
  overview: string;
  order: number;
  prerequisites: string[];
  lessons: Array<{
    id: string;
    title: string;
    objectives: Array<{ id: string; label: string }>;
    reliableCaseCount: number;
    available: boolean;
    mastery: number;
    assessedObjectiveCount: number;
    objectiveCount: number;
  }>;
  reliableCaseCount: number;
  available: boolean;
  mastery: number;
  assessedObjectiveCount: number;
  objectiveCount: number;
};

export type TutorMessageBody = {
  learnerId?: string;
  threadId?: string | null;
  mode: "tutorial" | "practice" | "freeform";
  lessonId?: string | null;
  /** Opaque ECG capability. The wire key remains `caseId` for API compatibility. */
  caseId?: EcgCapability | null;
  scopeKey?: string | null;
  message: string;
  viewerState?: Record<string, unknown>;
  clinicalContext?: ClinicalTutorContextRef | null;
  clinicalShiftContext?: ClinicalShiftTutorContextRef | null;
  adaptiveContext?: AdaptiveTutorContextRef | null;
  rapidRoundContext?: RapidRoundTutorContextRef | null;
  trainingSetContext?: TrainingSetTutorContextRef | null;
};

export type ClinicalTutorContextRef = {
  contextId: string;
  sessionId: string;
  itemId: string;
  answerId: number;
  version: "clinical-post-feedback-v1";
};

export type ClinicalShiftTutorContextRef = {
  contextId: string;
  sessionId: string;
  answerCount: number;
  version: "clinical-shift-debrief-v1";
};

export type AdaptiveTutorContextRef = {
  contextId: string;
  version: "adaptive-plan-coach-v1";
  expiresAt: string;
};

export type RapidRoundTutorContextRef = {
  roundId: string;
  answerCount: number;
  version: "rapid-round-debrief-v1";
};

export type TrainingSetTutorContextRef = {
  campaignId: string;
  answerCount: number;
  version: "training-set-debrief-v1";
};

export type ClickGradeBody = {
  lead: string;
  timeSec: number;
  amplitudeMv: number;
  concept?: string | null;
  guidedContext?: string | null;
};

export type RegionGradeBody = {
  lead: string;
  timeStartSec: number;
  timeEndSec: number;
  ampMinMv: number;
  ampMaxMv: number;
  concept?: string | null;
  guidedContext?: string | null;
};

function waveformPath(scope: WaveformScope | undefined, ecgRef: EcgCapability): string {
  const encodedRef = encodeURIComponent(ecgRef);
  if (scope?.kind === "guided") {
    return `/tutorials/${encodeURIComponent(scope.lessonId)}/waveform/${encodedRef}`;
  }
  if (scope?.kind === "training") {
    return `/training/campaigns/${encodeURIComponent(scope.campaignId)}/waveform/${encodedRef}`;
  }
  if (scope?.kind === "rapid") {
    return `/rapid/rounds/${encodeURIComponent(scope.roundId)}/waveform/${encodedRef}`;
  }
  if (scope?.kind === "clinical") {
    return `/clinical/shift/${encodeURIComponent(scope.sessionId)}/waveform/${encodedRef}`;
  }
  if (scope?.kind === "review") {
    return `/learning/sessions/${encodeURIComponent(scope.sessionRef)}/attempts/${encodeURIComponent(String(scope.attemptIndex))}/waveform/${encodedRef}`;
  }
  return `/cases/${encodedRef}/waveform`;
}

export type PathwaySceneStatus = "not-started" | "viewed" | "attempted" | "needs-review" | "complete" | "skipped";

export type PathwayProgressItem = {
  pathwayId: string;
  moduleId: string;
  sceneId: string;
  status: PathwaySceneStatus;
  activeInteractionIndex: number;
  completedActionIds: string[];
  state: Record<string, unknown>;
  source?: "server" | "guest_import";
  createdAt?: string;
  updatedAt?: string;
};

export type LearningResumeDestination =
  | { kind: "guided"; moduleId: string; sceneId: string | null }
  | { kind: "training" }
  | { kind: "rapid" }
  | { kind: "clinical" };

export type LearningResumeSession = {
  mode: "guided" | "training" | "rapid" | "clinical";
  phase: "deadline" | "feedback" | "in_progress";
  completed: number;
  total: number;
  updatedAt: string;
  destination: LearningResumeDestination;
};

export type LearningResumeSnapshot = {
  version: "learning-resume-v1";
  generatedAt: string;
  primary: LearningResumeSession | null;
  additional: LearningResumeSession[];
};

export type LearningActivityMode = "all" | "guided" | "training" | "rapid" | "clinical";

export type LearningActivityItem = {
  id: string;
  mode: Exclude<LearningActivityMode, "all">;
  kind: "guided_task" | "ecg_attempt";
  occurredAt: string;
  objectiveId: string | null;
  subskill: string | null;
  testedCompetencies: Array<{
    objectiveId: string;
    subskill: string;
    evidence: "formative" | "independent";
  }>;
  score: number | null;
  confidence: number | null;
  assistance: "unassisted" | "assisted" | "unknown";
  evidence: "formative" | "independent" | "legacy_unverified";
  reviewRecommended: boolean;
  review: {
    sessionRef: string;
    attemptIndex: number;
    sessionStatus: "complete" | "abandoned";
  } | null;
};

export type LearningActivityPage = {
  version: "learning-activity-v1";
  items: LearningActivityItem[];
  nextCursor: string | null;
  hasMore: boolean;
};

export type LearningSessionMode = "training" | "rapid" | "clinical";

export type LearningSessionCompetency = {
  objectiveId: string;
  subskill: string;
  mappingSource: "committed_event" | "session_focus";
};

export type LearningSessionSummary = {
  sessionRef: string;
  mode: LearningSessionMode;
  status: "complete" | "abandoned";
  attempted: number;
  total: number;
  score: number | null;
  correctCount: number | null;
  flaggedCount: number;
  focusCompetencies: LearningSessionCompetency[];
  startedAt: string;
  completedAt: string;
  reviewAvailable: boolean;
};

export type LearningSessionAttempt = {
  index: number;
  score: number | null;
  competencies: Array<LearningSessionCompetency & { score: number | null }>;
  confidence: number | null;
  assistance: { hintsUsed: number } | null;
  flagged: boolean;
};

export type LearningSessionPage = {
  version: "learning-sessions-v1";
  items: LearningSessionSummary[];
  hasMore: boolean;
  nextOffset: number | null;
  totalSavedItems: number;
};

export type LearningSessionReview = {
  version: "learning-session-review-v1";
  session: LearningSessionSummary;
  attempts: LearningSessionAttempt[];
};

export type LearningSessionFlagResult = {
  sessionRef: string;
  attemptIndex: number;
  flagged: boolean;
  flaggedCount: number;
};

export type LearningReplayWaveformPresentation = {
  kind: "twelve_lead" | "rhythm_strip";
  leads: string[];
};

export type LearningReplayTaskFeedback = {
  taskId: string;
  type?: string;
  topicId?: string;
  skillId?: string;
  objectiveId?: string;
  complete?: boolean;
  correct?: boolean;
  score?: number;
  timedOut?: boolean;
  formativeOnly?: boolean;
  feedback?: string;
  referenceLabel?: string;
  correctAnswer?: string;
  correctChoiceId?: string;
  expectedValue?: number;
  tolerance?: number;
  unit?: string;
  supportingFieldsReviewed?: string[];
  supportingFieldsEvidence?: string;
  absoluteError?: number;
  noTarget?: boolean;
  matchedRoi?: Record<string, unknown>;
};

export type LearningSessionReplay = {
  version: "learning-session-replay-v1";
  fidelity: "reconstructed";
  sessionRef: string;
  attemptIndex: number;
  mode: LearningSessionMode;
  sessionStatus: "complete" | "abandoned";
  displayId: string;
  submittedAt: string;
  ecgRef: EcgCapability;
  waveformAvailable: boolean;
  waveformPresentation: LearningReplayWaveformPresentation;
  comparison: {
    role: "prior";
    label: string;
    ecgRef: EcgCapability;
    waveformAvailable: boolean;
    waveformPresentation: LearningReplayWaveformPresentation;
    provenance: "same_patient_time_ordered_real_ecgs";
  } | null;
  question: Record<string, unknown> & {
    kind: LearningSessionMode;
    taskPacket?: RapidTaskPacket;
  };
  submission: Record<string, unknown> & {
    taskResponses?: Record<string, unknown>;
    viewerTaskEvidence?: ViewerTaskEvidence | null;
    traceEvidence?: ViewerTaskEvidence | null;
    structuredInterpretation?: Partial<Record<
      "rate" | "rhythm" | "axis" | "intervals" | "conduction" | "st_t" | "hypertrophy" | "synthesis",
      string
    >>;
  };
  feedback: Record<string, unknown> & {
    taskFeedback?: LearningReplayTaskFeedback[];
  };
  answerGuide: Record<string, unknown> & {
    systematicInterpretationComplete?: boolean;
    reviewedFramework?: Array<{
      key: string;
      label: string;
      review: string;
      grounded: boolean;
    }>;
  };
  /** Post-commit reviewed geometry. It is never present during an assessment. */
  reviewActions?: ViewerAction[];
  provenance: {
    tracing: "real_deidentified_ecg";
    context?: "authored_simulation";
    comparison?: "same_patient_time_ordered_real_ecgs";
    learningEvidence: string;
    contentLabel?: string;
  };
};

export type CompetencyTrendPoint = {
  occurredAt: string;
  score: number;
  mode: "guided" | "training" | "rapid" | "clinical";
  evidenceLevel: "guided" | "formative" | "independent_transfer" | "legacy_unverified";
  independent: boolean;
  recordStatus: "verified" | "legacy";
};

export type CompetencyTrend = {
  version: "competency-trend-v1";
  objectiveId: string;
  subskill: string;
  points: CompetencyTrendPoint[];
  pointCount: number;
  hasMore: boolean;
  interpretation: string;
};

export type LearningTrainingStage =
  | "not_set"
  | "preclinical"
  | "core_clerkship"
  | "advanced_clerkship"
  | "resident_review";

export type LearningPrimaryGoal =
  | "build_fundamentals"
  | "exam_prep"
  | "clinical_reading"
  | "emergency_prioritization"
  | "medication_safety";

export type LearningRapidPace = "untimed" | "ward" | "emergency";
export type LearningGuidanceLevel = "step_by_step" | "balanced" | "minimal";
export type LearningSessionLength = 5 | 10 | 25 | 50;

export type LearningPreferences = {
  trainingStage: LearningTrainingStage;
  primaryGoal: LearningPrimaryGoal;
  defaultSessionLength: LearningSessionLength;
  rapidPace: LearningRapidPace;
  guidanceLevel: LearningGuidanceLevel;
  reduceMotion: boolean;
  largeControls: boolean;
  updatedAt: string | null;
};

export type LearningPreferencesUpdate = Partial<Omit<LearningPreferences, "updatedAt">>;

export type StudyCalendarSettings = {
  timeZone: string;
  weekStartsOn: 0 | 1;
  saved: boolean;
  updatedAt: string | null;
};

export type StudyCalendarCompetency = {
  objectiveId: string;
  objectiveLabel: string;
  subskill: string;
  caseConcept: string;
  mode: "train" | "rapid";
  sourceDueAt: string;
  currentDueAt: string | null;
  sourceCurrent: boolean;
  launchHref: string | null;
};

export type StudyCalendarMode = "guided" | "train" | "rapid" | "clinical";

export type StudyCalendarActivity = {
  kind: "manual_mode" | "retention_review" | "study_plan";
  mode: StudyCalendarMode;
  objectiveId: string | null;
  objectiveLabel: string | null;
  subskill: string | null;
  caseConcept: string | null;
  sourceCurrent: boolean | null;
  launchHref: string | null;
};

export type StudyCalendarItem = {
  itemId: string;
  source: "manual" | "retention_review" | "study_plan";
  title: string;
  notes: string;
  scheduledDate: string;
  startMinute: number | null;
  durationMinutes: number | null;
  status: "scheduled" | "completed";
  completionSource: "manual" | "verified_practice" | null;
  completedAt: string | null;
  competency: StudyCalendarCompetency | null;
  activity: StudyCalendarActivity | null;
  revision: number;
  createdAt: string;
  updatedAt: string;
};

export type StudyCalendarReviewItem = {
  key: string;
  objectiveId: string;
  objectiveLabel: string;
  subskill: string;
  nextDueAt: string;
  dueState: "due" | "overdue" | "scheduled";
  overdueDays: number;
  plannedFor: string | null;
  scheduledItemId: string | null;
  launchHref: string | null;
  planPriority: number | null;
};

export type StudyCalendarReviewDay = {
  date: string;
  total: number;
  overdue: number;
  items: StudyCalendarReviewItem[];
};

export type StudyCalendarSnapshot = {
  version: "study-calendar-v1";
  generatedAt: string;
  range: { startDate: string; endDate: string };
  settings: StudyCalendarSettings;
  today: string;
  items: StudyCalendarItem[];
  reviewDays: StudyCalendarReviewDay[];
};

export type StudyCalendarItemCreate = {
  title: string;
  notes?: string;
  scheduledDate: string;
  startMinute?: number | null;
  durationMinutes?: number | null;
  mode?: StudyCalendarMode | null;
  clientRequestId: string;
};

export type StudyCalendarPlanCreate = {
  expectedActionKey: string;
  scheduledDate: string;
  startMinute?: number | null;
  durationMinutes?: number | null;
  notes?: string;
  clientRequestId: string;
};

export type StudyCalendarCompetencyCreate = {
  objectiveId: string;
  subskill: string;
  expectedNextDueAt: string;
  scheduledDate: string;
  startMinute?: number | null;
  durationMinutes?: number | null;
  notes?: string;
  clientRequestId: string;
};

export type StudyCalendarItemUpdate = {
  revision: number;
  title?: string;
  notes?: string;
  scheduledDate?: string;
  startMinute?: number | null;
  durationMinutes?: number | null;
};

export type CompetencyState = "unseen" | "acquiring" | "developing" | "consolidating" | "durable";

export type CompetencyCalendarProjection = {
  timeZone: string;
  today: string;
  reviewDays: Array<{ date: string; total: number }>;
};

export type CompetencyObjective = {
  objectiveId: string;
  label: string;
  domain: string;
  caseConcepts: string[];
  evidenceCeiling: string;
  subskills: Array<{
    subskill: string;
    state: CompetencyState;
    formativeScore: number;
    independentMastery: number;
    attempts: number;
    independentAttempts: number;
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
    independentEvidenceAvailable: boolean;
    independentReceipt: null | {
      mode: "train" | "rapid";
      caseConcept: string;
      receiptConcept: string;
      subskill: string;
    };
    evidenceUncertainty: string | null;
  }>;
};

export type AdaptivePriority = {
  objectiveId: string;
  label: string;
  domain: string;
  caseConcept: string;
  eligibleDistinct: number;
  subskill: string;
  state: CompetencyState;
  attempts: number;
  independentAttempts: number;
  independentMastery: number;
  highConfidenceWrong: number;
  isDue: boolean;
  dueState: "unseen" | "scheduled" | "due" | "overdue";
  overdueDays: number;
  nextDueAt: string | null;
  stabilityDays: number;
  distinctSuccessfulEcgs: number;
  distinctModes: number;
  lapses: number;
  reason: string;
};

export type AdaptiveCalendarAction = {
  version: "calendar-plan-action-v1";
  actionKey: string;
  relationship: "starting_check" | "follow_up" | "next_step";
  title: string;
  mode: "train" | "rapid";
  objectiveId: string;
  objectiveLabel: string | null;
  subskill: string;
  caseConcept: string;
  launchHref: string;
  suggestedDurationMinutes: number;
};

export type AdaptivePlan = {
  learnerId: string;
  coachContext: AdaptiveTutorContextRef;
  calendarAction: AdaptiveCalendarAction | null;
  generatedAt: string;
  plannerKind: "verified_competency_scheduler";
  generativeTutorUsed: false;
  basis: {
    independentCompetencyObservations: number;
    independentAttempts: number;
    independentAttemptUnit: "competency_observation";
    dueCompetencies: number;
    overdueCompetencies: number;
    highConfidenceMisses: number;
    eligibleConcepts: number;
    baselineNeeded: boolean;
  };
  primary: AdaptivePriority | null;
  priorities: AdaptivePriority[];
  stages: Array<{
    order: number;
    mode: "train" | "rapid" | "clinical";
    title: string;
    purpose: string;
    href: string;
    suggestedLength: number;
    receiptConcept: string;
    receiptSubskill: string;
    evidenceKind: "independent_transfer";
  }>;
  guidedRemediation: null | {
    mode: "guided";
    title: string;
    purpose: string;
    href: string;
    moduleId: string;
    sceneId: string;
    concept: string;
    evidenceKind: "formative_guided";
    updatesIndependentMastery: false;
    beforeStageOrder: number | null;
    reason: string;
  };
  integration: null | {
    primaryConcept: string;
    secondaryConcept: string;
    receiptConcept: string;
    receiptSubskill: "synthesize";
    prompt: string;
    href: string;
    suggestedLength: number;
  };
  clinicalApplication: null | {
    mode: "clinical";
    title: string;
    purpose: string;
    href: string;
    concept: string;
    subskill: "apply_in_context";
    evidenceKind: "formative_application";
    afterStageOrder: number | null;
    reason: string;
  };
  explanation: string;
};

export type GuestProgressSummary = {
  hasProgress: boolean;
  claimable: boolean;
  totalActivities: number;
  attempts: number;
  guidedInteractions: number;
  competencyReceipts: number;
  lessonScenes: number;
  tutorThreads: number;
  reviewSessions: number;
  rapidRounds: number;
  clinicalSessions: number;
  trainingCampaigns: number;
  competencies: number;
  learningPreferences: number;
  lastActivityAt: string | null;
};

export type GuestClaimReceipt = {
  claimed: true;
  replay: boolean;
  claimedAt: string;
  guestProgress: GuestProgressSummary;
};

export type AuthenticatedAuthResponse = {
  user: import("./types").User;
  guestClaim?: GuestClaimReceipt | null;
};

export type EmailVerificationRequiredResponse = {
  verificationRequired: true;
  challengeId: string;
  maskedEmail: string | null;
  expiresAt: string;
  guestClaimPendingVerification?: boolean;
  deliveryFailed?: boolean;
  retryAfterSeconds?: number | null;
};

export type UnverifiedEmailReplacementRequest = {
  currentPassword: string;
  newEmail: string;
  /** Present only for a public, still-pending registration. */
  challengeId?: string;
};

export type AccountResolutionResponse = {
  accountResolutionRequired: true;
  suggestedAction: "sign_in_or_reset_password" | "reset_password";
  message?: string;
};

export type EmailVerificationConfirmationResponse =
  | (AuthenticatedAuthResponse & { accountStatus: "verified" })
  | AccountResolutionResponse;

export type AuthAttemptResponse =
  | AuthenticatedAuthResponse
  | EmailVerificationRequiredResponse;

export type EmailChangeRequiredResponse = {
  emailChangeVerificationRequired: true;
  challengeId: string;
  maskedEmail: string | null;
  expiresAt: string;
  deliveryFailed?: boolean;
  retryAfterSeconds?: number | null;
};

export type CurrentEmailFactorRequiredResponse = {
  currentEmailFactorRequired: true;
  challengeId: string;
  maskedEmail: string | null;
  expiresAt: string;
  deliveryFailed?: boolean;
  retryAfterSeconds?: number | null;
};

export type EmailChangeRequestResponse =
  | EmailChangeRequiredResponse
  | CurrentEmailFactorRequiredResponse;

export type AuthResendResponse = {
  ok: true;
  message: string;
  deliveryFailed?: boolean;
  retryAfterSeconds?: number | null;
};

export type AuthApiErrorDetail = {
  field?: string | null;
  code?: string | null;
  message?: string | null;
};

export type ProgressExport = {
  schemaVersion: "ecg-student-progress-v2";
  exportedAt: string;
  assessmentPrivacy: {
    pendingAndFutureAnswerContractsOmitted: boolean;
    corpusIdentifiersPseudonymized?: boolean;
    note: string;
  };
  account: {
    userId: string;
    username: string;
    displayName: string;
    createdAt: string;
  };
  recordCounts: Record<string, number>;
  records: Record<string, Array<Record<string, unknown>>>;
};

export type AccountSession = {
  sessionId: string;
  createdAt: string;
  expiresAt: string;
  current: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/backend";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly field: string | null;
  readonly retryAfterSeconds: number | null;
  readonly detail: AuthApiErrorDetail | null;

  constructor(response: Response, rawBody: string, detail: AuthApiErrorDetail | null) {
    super(`${response.status} ${response.statusText}: ${rawBody}`);
    this.name = "ApiError";
    this.status = response.status;
    this.code = detail?.code ?? null;
    this.field = detail?.field ?? null;
    const retryAfter = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
    this.retryAfterSeconds = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null;
    this.detail = detail;
  }
}

/**
 * @deprecated Browser authentication is cookie-only. Kept temporarily so
 * older mode clients can omit their former Authorization branch without ever
 * receiving or reading a credential.
 */
export function getAuthToken(): null {
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    // Authentication is an HttpOnly SameSite cookie. Browser JavaScript never
    // reads, stores, or reconstructs the reusable session credential.
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    let detail: AuthApiErrorDetail | null = null;
    try {
      const parsed = JSON.parse(text) as { detail?: string | AuthApiErrorDetail };
      if (parsed.detail && typeof parsed.detail === "object") detail = parsed.detail;
      else if (typeof parsed.detail === "string") detail = { message: parsed.detail };
    } catch {
      // Preserve the opaque response body in the Error message for older
      // callers while structured auth clients use the safe fields above.
    }
    throw new ApiError(response, text, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  base: API_BASE,
  health: () => request<Record<string, unknown>>("/health"),
  datasetStatus: () => request<Record<string, unknown>>("/dataset/status"),
  cases: (opts?: { concept?: string; includeUncertain?: boolean; query?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (opts?.concept) params.set("concept", opts.concept);
    if (opts?.includeUncertain) params.set("includeUncertain", "true");
    if (opts?.query) params.set("query", opts.query);
    if (opts?.limit) params.set("limit", String(opts.limit));
    if (opts?.offset) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return request<CaseSummary[]>(`/cases${qs ? `?${qs}` : ""}`);
  },
  packet: (ecgRef: EcgCapability, opts?: { blinded?: boolean }) =>
    request<CasePacket>(`/cases/${encodeURIComponent(ecgRef)}/packet${opts?.blinded ? "?blinded=true" : ""}`),
  waveform: (ecgRef: EcgCapability, start = 0, end = 10, leads?: string[], scope?: WaveformScope) => {
    const params = new URLSearchParams();
    params.set("start", String(start));
    params.set("end", String(end));
    params.set("maxPoints", "1600");
    if (leads?.length) params.set("leads", leads.join(","));
    return request<WaveformResponse>(`${waveformPath(scope, ecgRef)}?${params.toString()}`);
  },
  concepts: () =>
    request<{
      concepts: Array<{ id: string; label: string; group: string; highYield?: boolean }>;
      practiceGroups: ConceptGroup[];
    }>("/concepts"),
  profile: (learnerId = "demo") => request<LearnerProfile>(`/learners/${learnerId}`),
  mastery: (learnerId = "demo") => request<LearnerProfile>(`/learners/${learnerId}/mastery`),
  nextCase: (learnerId = "demo", conceptId?: string, subskill?: string, excludeCaseIds: string[] = []) => {
    const params = new URLSearchParams({ learnerId });
    if (conceptId) params.set("conceptId", conceptId);
    if (subskill) params.set("subskill", subskill);
    if (excludeCaseIds.length) params.set("excludeCaseIds", excludeCaseIds.join(","));
    return request<{ case: CaseSummary | null; reason: string; targetObjectives: string[] }>(
      `/practice/next?${params.toString()}`,
    );
  },
  activeRapidRound: () => request<RapidRoundPayload>("/rapid/rounds/active"),
  startRapidRound: (body: unknown) =>
    request<RapidRoundPayload>("/rapid/rounds", { method: "POST", body: JSON.stringify(body) }),
  rapidRound: (roundId: string) => request<RapidRoundPayload>(`/rapid/rounds/${encodeURIComponent(roundId)}`),
  rapidResults: (roundId: string, offset = 0, limit = 5000) =>
    request<{ roundId: string; offset: number; limit: number; total: number; results: Array<Record<string, unknown>> }>(
      `/rapid/rounds/${encodeURIComponent(roundId)}/results?offset=${offset}&limit=${limit}`,
    ),
  nextRapidCase: (roundId: string, activate = false) =>
    request<RapidRoundPayload>(`/rapid/rounds/${encodeURIComponent(roundId)}/next`, {
      method: "POST",
      body: JSON.stringify({ activate }),
    }),
  submitRapidCase: (roundId: string, body: unknown) =>
    request<RapidRoundPayload>(`/rapid/rounds/${encodeURIComponent(roundId)}/submit`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  abandonRapidRound: (roundId: string) =>
    request<RapidRoundPayload>(`/rapid/rounds/${encodeURIComponent(roundId)}/abandon`, {
      method: "POST",
    }),
  trainingPool: (conceptId: string, subskill: string) => {
    const params = new URLSearchParams({ conceptId, subskill });
    return request<{
      conceptId: string;
      subskill: string;
      eligibleDistinct: number;
      roleCounts: { target: number; mimic: number; negative: number };
      allowedLengths: number[];
      source: "audited_waveform_only";
      independentReceiptsAvailable: boolean;
    }>(`/training/campaigns/pool?${params.toString()}`);
  },
  trainingAvailability: (conceptId: string) => {
    const params = new URLSearchParams({ conceptId });
    return request<{
      conceptId: string;
      source: "exact_target_index";
      subskills: Record<string, {
        available: boolean;
        independentReceiptsAvailable: boolean;
      }>;
    }>(`/training/campaigns/availability?${params.toString()}`);
  },
  activeTrainingCampaign: () => request<TrainingCampaignPayload>("/training/campaigns/active"),
  startTrainingCampaign: (body: unknown) =>
    request<TrainingCampaignPayload>("/training/campaigns", { method: "POST", body: JSON.stringify(body) }),
  trainingCampaign: (campaignId: string) =>
    request<TrainingCampaignPayload>(`/training/campaigns/${encodeURIComponent(campaignId)}`),
  nextTrainingCampaignCase: (campaignId: string) =>
    request<TrainingCampaignPayload>(`/training/campaigns/${encodeURIComponent(campaignId)}/next`, { method: "POST" }),
  submitTrainingCampaignCase: (campaignId: string, body: unknown) =>
    request<TrainingCampaignPayload>(`/training/campaigns/${encodeURIComponent(campaignId)}/submit`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  abandonTrainingCampaign: (campaignId: string) =>
    request<TrainingCampaignPayload>(`/training/campaigns/${encodeURIComponent(campaignId)}/abandon`, { method: "POST" }),
  submitAttempt: (body: unknown) =>
    request<{ attemptId: number; grade: Record<string, unknown>; tutor: TutorResponse; profile: LearnerProfile; packet: CasePacket }>("/attempts", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  recordGuidedEvent: (body: unknown) =>
    request<{
      eventId: number;
      requestedEvidenceLevel: string;
      effectiveEvidenceLevel: string;
      receipts: Array<{
        concept: string;
        subskill: string;
        formativeScore: number;
        independentMastery: number;
        evidenceLevel: string;
        retentionEligible: boolean;
        nextDueAt: string | null;
        stabilityDays: number;
        lapses: number;
        spacedRetrievals: number;
        distinctEligibleEcgs: number;
        distinctSuccessfulEcgs: number;
        dueState: "unseen" | "scheduled" | "due" | "overdue";
        intervalExpanded: boolean;
      }>;
    }>("/learning-events/guided", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tutorMessage: (body: TutorMessageBody) =>
    request<TutorMessageResponse>("/tutor/message", {
      method: "POST",
      body: JSON.stringify({ learnerId: "demo", ...body }),
    }),
  tutorThread: (threadId: string) => request<TutorThread>(`/tutor/thread/${encodeURIComponent(threadId)}`),
  tutorThreads: (opts: { mode?: string; lessonId?: string | null; ecgRef?: EcgCapability | null; scopeKey?: string | null; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts.mode) params.set("mode", opts.mode);
    if (opts.lessonId) params.set("lessonId", opts.lessonId);
    if (opts.ecgRef) params.set("caseId", opts.ecgRef);
    if (opts.scopeKey) params.set("scopeKey", opts.scopeKey);
    if (opts.limit) params.set("limit", String(opts.limit));
    return request<{ threads: Array<Omit<TutorThread, "messages">> }>(`/tutor/threads?${params.toString()}`);
  },
  gradeClick: (ecgRef: EcgCapability, body: ClickGradeBody) =>
    request<ClickGradeResult>(`/grade/click/${encodeURIComponent(ecgRef)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  gradeRegion: (ecgRef: EcgCapability, body: RegionGradeBody) =>
    request<RegionGradeResult>(`/grade/region/${encodeURIComponent(ecgRef)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  gradeGuidedMeasurement: (
    ecgRef: EcgCapability,
    body: {
      measurementKey: string;
      value: number;
      tolerance: number;
      derive?: "rr_from_heart_rate" | null;
      guidedContext: string;
    },
  ) => request<{ correct: boolean; noTarget: boolean; feedback: string }>(
    `/grade/measurement/${encodeURIComponent(ecgRef)}`,
    { method: "POST", body: JSON.stringify(body) },
  ),
  tutorials: () =>
    request<{
      frameworks: Array<{ id: string; title: string; steps: string[] }>;
      tutorials: Array<{ id: string; title: string; objectives: string[]; caseConcept: string | null; steps: string[] }>;
    }>("/tutorials"),
  curriculum: (learnerId = "demo") =>
    request<{ modules: CurriculumModule[] }>(`/curriculum?learnerId=${encodeURIComponent(learnerId)}`),
  pathwayProgress: (learnerId = "demo", pathwayId?: string) =>
    request<{ learnerId: string; items: PathwayProgressItem[] }>(
      `/learners/${encodeURIComponent(learnerId)}/pathway-progress${pathwayId ? `?pathwayId=${encodeURIComponent(pathwayId)}` : ""}`,
    ),
  savePathwayProgress: (
    learnerId: string,
    items: PathwayProgressItem[],
    source: "server" | "guest_import" = "server",
  ) => request<{ learnerId: string; items: PathwayProgressItem[] }>(
    `/learners/${encodeURIComponent(learnerId)}/pathway-progress`,
    {
      method: "POST",
      body: JSON.stringify({ learnerId, items, source, merge: true }),
    },
  ),
  competencies: (learnerId = "demo", timeZone?: string) => {
    return request<{ learnerId: string; registryVersion: string; objectives: CompetencyObjective[]; calendarProjection: CompetencyCalendarProjection }>(
      `/learners/${encodeURIComponent(learnerId)}/competencies`,
      timeZone ? { headers: { "X-ECG-Time-Zone": timeZone } } : undefined,
    );
  },
  competencyTrend: (objectiveId: string, subskill: string, limit = 20, learnerId = "demo") => {
    const params = new URLSearchParams({ limit: String(limit) });
    return request<CompetencyTrend>(
      `/learners/${encodeURIComponent(learnerId)}/competencies/${encodeURIComponent(objectiveId)}/${encodeURIComponent(subskill)}/trend?${params.toString()}`,
    );
  },
  learningResume: () => request<LearningResumeSnapshot>("/learning/resume"),
  learningActivity: (
    mode: LearningActivityMode = "all",
    limit = 20,
    cursor?: string | null,
  ) => {
    const params = new URLSearchParams({ mode, limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<LearningActivityPage>(`/learning/activity?${params.toString()}`);
  },
  learningSessions: (limit = 10, offset = 0, savedOnly = false) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (savedOnly) params.set("savedOnly", "true");
    return request<LearningSessionPage>(`/learning/sessions?${params.toString()}`);
  },
  learningSession: (sessionRef: string) =>
    request<LearningSessionReview>(`/learning/sessions/${encodeURIComponent(sessionRef)}`),
  learningSessionReplay: (sessionRef: string, attemptIndex: number) =>
    request<LearningSessionReplay>(
      `/learning/sessions/${encodeURIComponent(sessionRef)}/attempts/${encodeURIComponent(String(attemptIndex))}/replay`,
    ),
  setLearningSessionFlag: (sessionRef: string, attemptIndex: number, flagged: boolean) =>
    request<LearningSessionFlagResult>(
      `/learning/sessions/${encodeURIComponent(sessionRef)}/attempts/${encodeURIComponent(String(attemptIndex))}/flag`,
      { method: flagged ? "PUT" : "DELETE" },
    ),
  learningPreferences: () => request<LearningPreferences>("/learning/preferences"),
  updateLearningPreferences: (body: LearningPreferencesUpdate) =>
    request<LearningPreferences>("/learning/preferences", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  learningCalendar: (startDate: string, endDate: string, timeZone: string) => {
    const params = new URLSearchParams({ startDate, endDate, timeZone });
    return request<StudyCalendarSnapshot>(`/learning/calendar?${params.toString()}`);
  },
  updateLearningCalendarSettings: (body: { timeZone: string; weekStartsOn: 0 | 1 }) =>
    request<StudyCalendarSettings>("/learning/calendar/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  createLearningCalendarItem: (body: StudyCalendarItemCreate) =>
    request<StudyCalendarItem>("/learning/calendar/items", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createLearningCalendarItemFromCompetency: (body: StudyCalendarCompetencyCreate) =>
    request<StudyCalendarItem>("/learning/calendar/items/from-competency", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createLearningCalendarItemFromPlan: (body: StudyCalendarPlanCreate) =>
    request<StudyCalendarItem>("/learning/calendar/items/from-plan", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateLearningCalendarItem: (itemId: string, body: StudyCalendarItemUpdate) =>
    request<StudyCalendarItem>(`/learning/calendar/items/${encodeURIComponent(itemId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteLearningCalendarItem: (itemId: string, revision: number) =>
    request<{ deleted: true; itemId: string }>(
      `/learning/calendar/items/${encodeURIComponent(itemId)}?revision=${encodeURIComponent(String(revision))}`,
      { method: "DELETE" },
    ),
  completeLearningCalendarItem: (itemId: string, revision: number) =>
    request<StudyCalendarItem>(`/learning/calendar/items/${encodeURIComponent(itemId)}/completion`, {
      method: "PUT",
      body: JSON.stringify({ revision }),
    }),
  reopenLearningCalendarItem: (itemId: string, revision: number) =>
    request<StudyCalendarItem>(
      `/learning/calendar/items/${encodeURIComponent(itemId)}/completion?revision=${encodeURIComponent(String(revision))}`,
      { method: "DELETE" },
    ),
  adaptivePlan: () => request<AdaptivePlan>("/adaptive/plan"),
  tutorial: (
    lessonId: string,
    conceptId?: string,
    excludeCaseId?: string,
    eligibility?: {
      minimumTier?: "A" | "B";
      requiredLeads?: string[];
      requiredMeasurements?: string[];
      requiredRois?: string[];
      requiresPerBeatLandmarks?: boolean;
    },
  ) =>
    request<{
      lesson: TutorialLesson;
      frameworks: Array<{ id: string; title: string; steps: string[] }>;
      recommendedCase: CaseSummary;
      recommendedPacket: CasePacket;
      guidedContext: string;
      guidedEligibility: {
        eligible: boolean;
        missingRequirementCount: number;
        message: string;
      };
      openingPrompt: string;
      assessmentPrivacy: {
        opaqueEcgReference: true;
        answerFieldsWithheldUntilCommit: true;
        sourceRecordIdentityWithheld: true;
      };
      selection?: { requestedConceptUnavailable?: boolean; reason?: string; excludedBorderlineCount?: number };
    }>(`/tutorials/${lessonId}${(() => {
      const params = new URLSearchParams();
      if (conceptId) params.set("concept", conceptId);
      if (excludeCaseId) params.set("excludeCaseId", excludeCaseId);
      if (eligibility?.minimumTier) params.set("minimumTier", eligibility.minimumTier);
      if (eligibility?.requiredLeads?.length) params.set("requiredLeads", eligibility.requiredLeads.join(","));
      if (eligibility?.requiredMeasurements?.length) params.set("requiredMeasurements", eligibility.requiredMeasurements.join(","));
      if (eligibility?.requiredRois?.length) params.set("requiredRois", eligibility.requiredRois.join(","));
      if (eligibility?.requiresPerBeatLandmarks) params.set("requiresPerBeatLandmarks", "true");
      const query = params.toString();
      return query ? `?${query}` : "";
    })()}`),
  guestProgress: () => request<GuestProgressSummary>("/auth/guest-progress"),
  claimLegacyProgress: () =>
    request<{ ok: true; guestClaim: GuestClaimReceipt }>("/auth/guest-progress/claim", {
      method: "POST",
      body: "{}",
    }),
  deleteGuestProgress: () =>
    request<{ ok: boolean; deletedRecords: number }>("/auth/guest-progress", { method: "DELETE" }),
  register: (body: { password: string; email: string; displayName?: string; claimGuestProgress?: boolean }) =>
    request<AuthAttemptResponse>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body: { identifier: string; password: string; claimGuestProgress?: boolean }) =>
    request<AuthAttemptResponse>("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  confirmEmailVerification: (body: { challengeId: string; token: string; password: string }) =>
    request<EmailVerificationConfirmationResponse>("/auth/email/verify/confirm", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resendEmailVerification: (body: { challengeId: string }) =>
    request<AuthResendResponse>("/auth/email/verify/resend", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  replaceUnverifiedEmail: (body: UnverifiedEmailReplacementRequest) =>
    request<EmailVerificationRequiredResponse>("/auth/email/unverified/replace", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  requestPasswordReset: (body: { email: string }) =>
    request<{ ok: true; message: string }>("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  confirmPasswordReset: (body: {
    challengeId: string;
    token: string;
    newPassword: string;
    recoveryUsername?: string;
    recoveryDisplayName?: string;
  }) =>
    request<{
      ok: true;
      identityRecovered?: boolean;
      username?: string | null;
      displayName?: string | null;
    }>("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  requestEmailUpgrade: (body: { email: string; currentPassword: string }) =>
    request<EmailVerificationRequiredResponse>("/auth/email/upgrade/request", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  requestEmailChange: (body: { email: string; currentPassword: string }) =>
    request<EmailChangeRequestResponse>("/auth/email/change/request", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  confirmEmailChangeCurrentFactor: (body: { challengeId: string; code: string }) =>
    request<EmailChangeRequiredResponse>("/auth/email/change/current-factor/confirm", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resendEmailChangeCurrentFactor: (body: { challengeId: string }) =>
    request<AuthResendResponse>("/auth/email/change/current-factor/resend", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  confirmEmailChange: (body: { challengeId: string; token: string }) =>
    request<{ ok: true; user: import("./types").User }>("/auth/email/change/confirm", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resendEmailChange: (body: { challengeId: string }) =>
    request<AuthResendResponse>("/auth/email/change/resend", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  logoutAll: () => request<{ ok: boolean; revokedSessions: number }>("/auth/logout-all", { method: "POST" }),
  logoutOthers: () =>
    request<{ ok: boolean; revokedOtherSessions: number }>("/auth/logout-others", { method: "POST" }),
  sessions: () => request<{ sessions: AccountSession[] }>("/auth/sessions"),
  revokeSession: (sessionId: string) =>
    request<{ ok: boolean; revokedSessionId: string }>(`/auth/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),
  changePassword: (body: { currentPassword: string; newPassword: string }) =>
    request<{ user: import("./types").User; revokedOtherSessions: boolean }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  authorizeExport: (body: { currentPassword: string }) =>
    request<{ ok: boolean; expiresAt: string }>("/auth/export/authorize", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  exportProgress: () => request<ProgressExport>("/auth/export", { method: "POST" }),
  deleteAccount: (body: { currentPassword: string; confirmation: string }) =>
    request<{ ok: boolean }>("/auth/account", {
      method: "DELETE",
      body: JSON.stringify(body),
    }),
  me: () => request<MeResponse>("/auth/me"),
};
