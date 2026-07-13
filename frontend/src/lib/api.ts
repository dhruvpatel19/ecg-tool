import type {
  CasePacket,
  CaseSummary,
  ClickGradeResult,
  ClickTask,
  ConceptGroup,
  LearnerProfile,
  MeResponse,
  RegionGradeResult,
  RapidRoundPayload,
  TrainingCampaignPayload,
  TutorMessageResponse,
  TutorResponse,
  TutorThread,
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
  }>;
  reliableCaseCount: number;
  available: boolean;
  mastery: number;
};

export type TutorMessageBody = {
  learnerId?: string;
  threadId?: string | null;
  mode: "tutorial" | "practice" | "freeform";
  lessonId?: string | null;
  caseId?: string | null;
  message: string;
  viewerState?: Record<string, unknown>;
};

export type ClickGradeBody = {
  lead: string;
  timeSec: number;
  amplitudeMv: number;
  concept?: string | null;
};

export type RegionGradeBody = {
  lead: string;
  timeStartSec: number;
  timeEndSec: number;
  ampMinMv: number;
  ampMaxMv: number;
  concept?: string | null;
};

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

export type CompetencyState = "unseen" | "acquiring" | "developing" | "consolidating" | "durable";

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

export type AdaptivePlan = {
  learnerId: string;
  generatedAt: string;
  plannerKind: "verified_competency_scheduler";
  generativeTutorUsed: false;
  basis: {
    independentAttempts: number;
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
  integration: null | {
    primaryConcept: string;
    secondaryConcept: string;
    receiptConcept: string;
    receiptSubskill: "synthesize";
    prompt: string;
    href: string;
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
  lastActivityAt: string | null;
};

export type GuestClaimReceipt = {
  claimed: true;
  replay: boolean;
  claimedAt: string;
  guestProgress: GuestProgressSummary;
};

type AuthResponse = {
  user: import("./types").User;
  guestClaim?: GuestClaimReceipt | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/backend";

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
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
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
  packet: (caseId: string, opts?: { blinded?: boolean }) =>
    request<CasePacket>(`/cases/${caseId}/packet${opts?.blinded ? "?blinded=true" : ""}`),
  waveform: (caseId: string, start = 0, end = 10, leads?: string[]) => {
    const params = new URLSearchParams();
    params.set("start", String(start));
    params.set("end", String(end));
    params.set("maxPoints", "1600");
    if (leads?.length) params.set("leads", leads.join(","));
    return request<WaveformResponse>(`/cases/${caseId}/waveform?${params.toString()}`);
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
  trainingPool: (conceptId: string, subskill: string) => {
    const params = new URLSearchParams({ conceptId, subskill });
    return request<{
      conceptId: string;
      subskill: string;
      eligibleDistinct: number;
      roleCounts: { target: number; mimic: number; negative: number };
      allowedLengths: number[];
      source: "audited_waveform_only";
    }>(`/training/campaigns/pool?${params.toString()}`);
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
    request<{ attemptId: number; grade: Record<string, unknown>; tutor: TutorResponse; profile: LearnerProfile }>("/attempts", {
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
  tutorThreads: (opts: { mode?: string; lessonId?: string | null; caseId?: string | null; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts.mode) params.set("mode", opts.mode);
    if (opts.lessonId) params.set("lessonId", opts.lessonId);
    if (opts.caseId) params.set("caseId", opts.caseId);
    if (opts.limit) params.set("limit", String(opts.limit));
    return request<{ threads: Array<Omit<TutorThread, "messages">> }>(`/tutor/threads?${params.toString()}`);
  },
  gradeClick: (caseId: string, body: ClickGradeBody) =>
    request<ClickGradeResult>(`/grade/click/${encodeURIComponent(caseId)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  gradeRegion: (caseId: string, body: RegionGradeBody) =>
    request<RegionGradeResult>(`/grade/region/${encodeURIComponent(caseId)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
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
  competencies: (learnerId = "demo") =>
    request<{ learnerId: string; registryVersion: string; objectives: CompetencyObjective[] }>(
      `/learners/${encodeURIComponent(learnerId)}/competencies`,
    ),
  adaptivePlan: () => request<AdaptivePlan>("/adaptive/plan"),
  tutorial: (lessonId: string, conceptId?: string, excludeCaseId?: string) =>
    request<{
      lesson: TutorialLesson;
      frameworks: Array<{ id: string; title: string; steps: string[] }>;
      recommendedCase: CaseSummary;
      openingPrompt: string;
      selection?: { requestedConceptUnavailable?: boolean; reason?: string; targetObjectives?: string[]; exemplarRejections?: Array<{ caseId: string; reasons: string[] }> };
    }>(`/tutorials/${lessonId}${(() => {
      const params = new URLSearchParams();
      if (conceptId) params.set("concept", conceptId);
      if (excludeCaseId) params.set("excludeCaseId", excludeCaseId);
      const query = params.toString();
      return query ? `?${query}` : "";
    })()}`),
  guestProgress: () => request<GuestProgressSummary>("/auth/guest-progress"),
  register: (body: { username: string; password: string; displayName?: string; claimGuestProgress?: boolean }) =>
    request<AuthResponse>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body: { username: string; password: string; claimGuestProgress?: boolean }) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  logoutAll: () => request<{ ok: boolean; revokedSessions: number }>("/auth/logout-all", { method: "POST" }),
  changePassword: (body: { currentPassword: string; newPassword: string }) =>
    request<{ user: import("./types").User; revokedOtherSessions: boolean }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  me: () => request<MeResponse>("/auth/me"),
};
