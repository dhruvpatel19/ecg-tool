// Clinical Decisions mode — frontend types + API client.
// Mirrors the backend blinded item / grade contract (snake_case keys from the API).

import { api, getAuthToken } from "./api";
import type { ViewerAction } from "./types";

export type Lane = "clinic" | "ward" | "ed";
export type Mode = "learn" | "shift";
export type QuestionType = "triage" | "stepwise" | "click" | "spoterror" | "oldnew" | "mcq";

export type ClinicalOption = {
  id: string;
  text: string;
  value?: string | null;
};

export type StepOption = { text: string };
export type StepwiseStep = { prompt: string; options: StepOption[] };
export type MachineLine = { id: string; text: string };
export type StemChips = {
  age?: number | null;
  setting?: string | null;
  symptom?: string | null;
  bp?: string | null;
  mental_status?: string | null;
};
export type DisplaySpec = {
  mode: "twelve_lead" | "twelve_lead_pinned_strip" | "twelve_lead_machine_panel" | "stacked_twelve_lead" | "zoom_lead";
  pinned_strip_lead?: string | null;
  zoom_lead?: string | null;
  tested_scope: "full_12_lead" | "rhythm_only" | "zoom_lead";
};

// A blinded item as served by /clinical/shift/{id}/next (answer key stripped).
export type BlindedItem = {
  item_id: string;
  ecg_id: string;
  prior_ecg_id?: string | null;
  situation: Lane;
  question_type: QuestionType;
  stem: string;
  chips?: StemChips;
  prompt?: string;
  options?: ClinicalOption[];
  steps?: StepwiseStep[];
  machine_read?: MachineLine[];
  display_spec: DisplaySpec;
  clickable_leads?: string[];
  click_target_type?: string | null;
  /** Neutral parsed waveform ROI for viewer grading; never a pathology answer key. */
  click_roi_concept?: string | null;
  tracing_provenance?: "real_deidentified_ecg" | "synthetic_teaching_waveform";
  context_provenance?: "authored_simulation";
  learning_evidence?: "formative_only";
  content_label?: string;
};

// Honest provenance badge driven by the item's data (round-3 audit).
export function provenanceBadge(p?: string): string {
  return p === "real_deidentified_ecg"
    ? "Real de-identified ECG · authored vignette"
    : "Synthetic teaching ECG · authored simulation";
}

export type ClockSpec = {
  untimed?: boolean;
  orientSec?: number;
  decideSec?: number;
  activePhase?: "orient" | "decide";
  phaseStartedAt?: string | null;
  phaseDeadlineAt?: string | null;
  orientStartedAt?: string | null;
  orientDeadlineAt?: string | null;
  decideStartedAt?: string | null;
  decideDeadlineAt?: string | null;
};

export type NextResult = {
  item: BlindedItem | null;
  itemId?: string;
  index: number;
  total: number;
  done: boolean;
  reason?: string;
  clock?: ClockSpec;
  contextRevealed?: boolean;
  firstLook?: { firstLookFinding: string; firstLookConfidence: number } | null;
};

export type AxisScore = Record<string, number>;

export type ClinicalGrade = {
  caseId: string;
  score: number;
  correctObjectives: string[];
  missedObjectives: string[];
  feedback: string;
  teachingPoints: string[];
  answerClass: string | null;
  axisScores: AxisScore;
  safetyFlags: string[];
  calibrationEvent: Record<string, unknown>;
  timedOut: boolean;
  viewerActions: ViewerAction[];
  stemDisclosedObjectives?: string[];
  ecgRecognitionSuppressed?: boolean;
  clinicalApplicationEvidence?: "formative_only";
  competencyReceipts?: Array<{
    concept: string;
    subskill: "apply_in_context" | "localize";
    score: number;
    correct: boolean;
    formativeScore: number;
    independentMastery: number;
    evidenceLevel: "guided";
    formativeOnly: true;
    retentionEligible: false;
    nextDueAt: string | null;
    evidenceSource: "clinical_action_server_grade" | "clinical_trace_roi_server_grade";
  }>;
  stepResults?: boolean[];
};

export type ShiftSession = {
  sessionId: string;
  learnerId: string;
  lane: Lane;
  tier: Mode;
  focusObjective?: string | null;
  focusSubskill?: string | null;
  length: number;
  pendingItemId?: string | null;
  feedbackItemId?: string | null;
  contextRevealed?: boolean;
  firstLook?: { firstLookFinding: string; firstLookConfidence: number } | null;
  orientStartedAt?: string | null;
  orientDeadlineAt?: string | null;
  decideStartedAt?: string | null;
  decideDeadlineAt?: string | null;
  position: number;
  status: string;
};

export type ShiftReport = {
  sessionId: string;
  lane: Lane;
  tier: Mode;
  answered: number;
  length: number;
  accuracy: number;
  bestStreak: number;
  avgDecideMs: number | null;
  calibrationLabel: string;
  status: string;
};

export type ClinicalAnswerPayload = {
  /** ECG-only commitment captured before the authored context is revealed. */
  firstLookFinding?: string | null;
  firstLookConfidence?: number | null;
  selectedOptionId?: string | null;
  click?: { lead: string; timeSec: number; amplitudeMv?: number } | null;
  machineLineId?: string | null;
  confidence?: number | null;
  answerTimeMs?: number | null;
  confidenceTimeMs?: number | null;
  timedOut?: boolean;
  stepAnswers?: number[];
};

export type ClinicalLifecycle = {
  session: ShiftSession | null;
  state: "picker" | "orient" | "decide" | "feedback" | "report";
  current: NextResult | null;
  grade: ClinicalGrade | null;
  answer?: ClinicalAnswerPayload | null;
  report: ShiftReport | null;
};

// Situation-scaled clock (§16D). Pilot defaults — must mirror backend clinical/constants.py;
// the server also returns a clock spec per item, which takes precedence when present.
export const LANE_LABEL: Record<Lane, string> = { clinic: "Clinic", ward: "Ward", ed: "Emergency dept" };
export const ACUTE_LANES: Lane[] = ["ed"];

export function phaseLabels(lane: Lane): { orient: string; decide: string } {
  return ACUTE_LANES.includes(lane)
    ? { orient: "First look", decide: "Commit action" }
    : { orient: "Orient", decide: "Decide" };
}

const API = process.env.NEXT_PUBLIC_API_BASE ?? "/api/backend";

async function post<T>(path: string, body: unknown): Promise<T> {
  const token = getAuthToken();
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const token = getAuthToken();
  const res = await fetch(`${API}${path}`, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const clinicalApi = {
  bankStatus: () => get<{ counts: Record<string, number> }>("/clinical/bank/status"),
  bankCoverage: () => get<{
    coverage: Record<string, { items: number; distinctEcgs: number }>;
    clinicianReviewed: boolean;
    reviewStatus: string;
  }>("/clinical/bank/coverage"),
  start: (body: { lane: Lane; tier: Mode; length: number; learnerId?: string; focus?: string; subskill?: string }) =>
    post<{ session: ShiftSession; next: NextResult }>("/clinical/shift/start", body),
  active: () => get<ClinicalLifecycle>("/clinical/shift/active"),
  next: (sessionId: string) => post<NextResult>(`/clinical/shift/${sessionId}/next`, {}),
  activatePhase: (sessionId: string, itemId: string, phase: "orient" | "decide") =>
    post<NextResult>(`/clinical/shift/${sessionId}/phase`, { itemId, phase }),
  revealContext: (sessionId: string, itemId: string, answer: ClinicalAnswerPayload) =>
    post<NextResult>(`/clinical/shift/${sessionId}/context`, { itemId, answer }),
  answer: (sessionId: string, itemId: string, answer: ClinicalAnswerPayload) =>
    post<{ grade: ClinicalGrade }>(`/clinical/shift/${sessionId}/answer`, { itemId, answer }),
  report: (sessionId: string) => get<ShiftReport>(`/clinical/shift/${sessionId}/report`),
  // re-export the shared waveform client (used by the pinned rhythm strip)
  waveform: api.waveform,
};
