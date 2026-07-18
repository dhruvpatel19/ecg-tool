"use client";

import { ArrowLeft, ArrowRight, BookOpenCheck, CheckCircle2, Clock, LayoutDashboard, RefreshCw, RotateCcw, Sparkles, Stethoscope, Timer } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import {
  LearningWorkspaceShell,
  ResponseRail,
  SessionBar,
  TutorDrawer,
  WaveformPane,
  WorkspaceBody,
  WorkspaceNotices,
} from "@/components/layout/LearningWorkspaceShell";
import { conceptLabel, type ECGPoint } from "@/lib/coordinates";
import {
  clinicalApi,
  LANE_LABEL,
  phaseLabels,
  provenanceBadge,
  type ClinicalAnswerPayload,
  type ClinicalGrade,
  type Lane,
  type Mode,
  type NextResult,
  type ShiftReport,
  type ShiftSession,
  type StepwiseStageMetadata,
} from "@/lib/clinical";
import {
  ClinicalEvidenceTimeline,
  ClinicalImmediateReview,
  ClinicalJourneyProgress,
  ClinicalPatientSnapshot,
  ClinicalSetReviewExperience,
  ClinicalSetupExperience,
  buildClinicalDomainSummaries,
  buildClinicalJourney,
  type ClinicalCaseReviewItem,
  type ClinicalSBIFeedback,
} from "./ClinicalExperience";
import { useAuth } from "@/lib/auth";
import { api, type ClinicalTutorContextRef } from "@/lib/api";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import { parseLearningReturn } from "@/lib/learning/learningReturn";
import { useLearningPreferences } from "@/lib/useLearningPreferences";
import type { ViewerAction, ViewerTaskEvidence, ViewerTaskSpec } from "@/lib/types";

type View = "picker" | "runner" | "report";
type Phase = "orient" | "decide" | "feedback";

const LANES: Lane[] = ["clinic", "ward", "ed"];
const LENGTHS = [5, 10];
const CLINICAL_RETURN_SURFACES = ["lesson", "study_plan", "rapid"] as const;
const FIRST_LOOK_OPTIONS = [
  ["normal_or_no_dominant_abnormality", "Normal / no dominant abnormality"],
  ["rate_or_rhythm", "Rate or rhythm abnormality"],
  ["conduction_or_interval", "Conduction or interval abnormality"],
  ["st_t_or_ischemia", "ST–T / ischemia pattern"],
  ["chamber_or_voltage", "Chamber / voltage pattern"],
  ["uncertain", "Uncertain — need clinical context"],
] as const;

function skillLabel(value: string) {
  const labels: Record<string, string> = {
    apply_in_context: "use in context",
    calibrate_confidence: "calibrate confidence",
    discriminate: "tell apart",
    explain_mechanism: "explain",
    localize: "locate",
    measure: "measure",
    recognize: "identify",
    synthesize: "complete interpretation",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function humanLabel(value: string) {
  const labels: Record<string, string> = {
    concept_identification: "Finding",
    ecg_sequence: "ECG sequence",
    evidence_source_matching: "Evidence boundaries",
    ecg_evidence: "ECG-supported fact",
    authored_context_boundary: "Vignette-only fact",
    unsupported_claim_boundary: "Unsupported claim",
    measurement_accuracy: "Measurement",
    missing_required_safety_action: "A required safety action was missing",
  };
  const text = labels[value] ?? value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function readableApiError(caught: unknown, fallback: string) {
  const detail = caught instanceof Error ? caught.message : "";
  if (!detail || /^\d{3}\b/.test(detail) || /internal server error|failed to fetch|networkerror/i.test(detail)) return fallback;
  return detail;
}

function clinicalStageLabel(stageKind: StepwiseStageMetadata["stage_kind"]) {
  const labels = {
    ecg: "ECG interpretation",
    decision: "Clinical decision",
    reassessment: "Reassessment",
    handoff: "Handoff",
  } as const;
  return stageKind ? labels[stageKind] : "Patient update";
}

function hasEpisodeStageMetadata(stage: StepwiseStageMetadata) {
  return Boolean(
    stage.stage_kind
    || stage.stage_title
    || stage.elapsed_label
    || stage.clinical_update
    || stage.data_points?.length,
  );
}

function ClinicalEpisodeStageUpdate({
  stage,
  stepNumber,
  status,
}: {
  stage: StepwiseStageMetadata;
  stepNumber: number;
  status: "active" | "committed";
}) {
  const headingId = useId();
  if (!hasEpisodeStageMetadata(stage)) return null;
  const title = stage.stage_title || clinicalStageLabel(stage.stage_kind);
  const statusLabel = status === "active" ? "Current patient update" : "Completed patient update";
  const stageSources = new Set(stage.data_points?.map((point) => point.source).filter(Boolean));
  const sourceLabel = stageSources.has("authored_simulation")
    ? "Authored simulation"
    : stageSources.has("source_metadata")
      ? "Source-verified comparison metadata"
      : null;
  return (
    <article
      className="clinical-episode-update"
      data-status={status}
      aria-labelledby={headingId}
      role={status === "active" ? "status" : undefined}
      aria-live={status === "active" ? "polite" : undefined}
      aria-atomic={status === "active" ? true : undefined}
    >
      <span className="sr-only">{statusLabel}</span>
      <header>
        <div>
          <span className="clinical-episode-stage-kind">{clinicalStageLabel(stage.stage_kind)} · Stage {stepNumber}</span>
          <h3 id={headingId}>{title}</h3>
        </div>
        {stage.elapsed_label ? <span className="clinical-episode-elapsed"><Clock size={13} aria-hidden="true" /> {stage.elapsed_label}</span> : null}
      </header>
      {sourceLabel ? (
        <span
          className="clinical-episode-source"
          data-source={stageSources.has("authored_simulation") ? "authored" : "source"}
        >
          {sourceLabel}
        </span>
      ) : null}
      {stage.clinical_update ? <p>{stage.clinical_update}</p> : null}
      {stage.data_points?.length ? (
        <dl className="clinical-episode-data" aria-label={`${title} clinical data`}>
          {stage.data_points.map((point, index) => (
            <div key={`${point.label}-${index}`}>
              <dt>{point.label}</dt>
              <dd>
                <strong>{point.value}</strong>
                {point.trend ? <span className="clinical-episode-trend">{humanLabel(point.trend)}</span> : null}
                {point.detail ? <small>{point.detail}</small> : null}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}

export function ClinicalDecisions() {
  const { identityKey } = useAuth();
  const { preferences, loading: preferencesLoading } = useLearningPreferences();
  const [view, setView] = useState<View>("picker");
  const [hydrationRetryKey, setHydrationRetryKey] = useState(0);
  const [lane, setLane] = useState<Lane>("clinic");
  const [mode, setMode] = useState<Mode>("learn");
  const [length, setLength] = useState(5);

  const [session, setSession] = useState<ShiftSession | null>(null);
  const [current, setCurrent] = useState<NextResult | null>(null);
  const [phase, setPhase] = useState<Phase>("orient");
  const [answer, setAnswer] = useState<ClinicalAnswerPayload>({});
  const [stepDraft, setStepDraft] = useState<number | null>(null);
  const [grade, setGrade] = useState<ClinicalGrade | null>(null);
  const [tutorContext, setTutorContext] = useState<ClinicalTutorContextRef | null>(null);
  const [report, setReport] = useState<ShiftReport | null>(null);
  const [reportCoach, setReportCoach] = useState<{ tutorMessage: string; socraticQuestion?: string | null; suggestedNextStep?: string | null } | null>(null);
  const [reportCoachBusy, setReportCoachBusy] = useState(false);
  const [reportCoachError, setReportCoachError] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [leaveAfterAbandon, setLeaveAfterAbandon] = useState("");
  const [busy, setBusy] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [returnTo, setReturnTo] = useState("");
  const [handoffFocus, setHandoffFocus] = useState("");
  const [handoffSubskill, setHandoffSubskill] = useState<LearningSubskill | null>(null);
  const [competencyReceipt, setCompetencyReceipt] = useState<string | null>(null);
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [handoffUnavailable, setHandoffUnavailable] = useState("");
  const [activeShiftIntentConflict, setActiveShiftIntentConflict] = useState("");
  const [coverageReady, setCoverageReady] = useState(false);
  const [aiViewerActions, setAiViewerActions] = useState<ViewerAction[]>([]);
  const [reviewActionStep, setReviewActionStep] = useState(0);
  const [reviewPlaybackKey, setReviewPlaybackKey] = useState(0);
  const contextRef = useRef<HTMLDivElement | null>(null);
  const submissionRef = useRef(false);
  const abandonTriggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogTriggerRef = useRef<HTMLButtonElement | null>(null);
  const abandonDialogRef = useRef<HTMLElement | null>(null);
  const keepWorkingRef = useRef<HTMLButtonElement | null>(null);
  const lengthChoiceSourceRef = useRef<"untouched" | "preference" | "explicit" | "restored" | "user">("untouched");
  const returnDestination = parseLearningReturn(returnTo, CLINICAL_RETURN_SURFACES);
  const handoffSource = returnDestination?.surface === "study_plan"
    ? "study plan"
    : returnDestination?.surface === "lesson" ? "lesson" : "selected focus";

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
    const frame = window.requestAnimationFrame(() => keepWorkingRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [confirmAbandon]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedReturn = parseLearningReturn(params.get("returnTo"), CLINICAL_RETURN_SURFACES);
    setReturnTo(requestedReturn?.href ?? "");
    const requestedFocus = params.get("focus") ?? "";
    setHandoffFocus(requestedFocus);
    const requestedSubskill = params.get("subskill");
    if (isLearningSubskill(requestedSubskill)) setHandoffSubskill(requestedSubskill);
    const requestedLane = params.get("lane");
    if (requestedLane && LANES.includes(requestedLane as Lane)) setLane(requestedLane as Lane);
    const requestedLength = Number(params.get("length"));
    if (LENGTHS.includes(requestedLength)) {
      lengthChoiceSourceRef.current = "explicit";
      setLength(requestedLength);
    }
  }, []);

  useEffect(() => {
    const context = report?.tutorContext;
    const prompt = report?.debrief?.aiPrompt;
    if (view !== "report" || !context || !prompt) return;
    let cancelled = false;
    setReportCoachBusy(true);
    setReportCoachError("");
    void (async () => {
      try {
        const existing = await api.tutorThreads({
          mode: "practice",
          lessonId: context.contextId,
          ecgRef: null,
          limit: 1,
        });
        const threadSummary = existing.threads[0];
        if (threadSummary) {
          const thread = await api.tutorThread(threadSummary.threadId);
          const latest = [...thread.messages].reverse().find((message) => message.role === "tutor");
          if (latest) {
            if (!cancelled) {
              setReportCoach({
                tutorMessage: latest.content,
                socraticQuestion: typeof latest.meta.socraticQuestion === "string" ? latest.meta.socraticQuestion : null,
                suggestedNextStep: typeof latest.meta.suggestedNextStep === "string" ? latest.meta.suggestedNextStep : null,
              });
            }
            return;
          }
        }
        const response = await api.tutorMessage({
          mode: "practice",
          lessonId: context.contextId,
          caseId: null,
          message: prompt,
          viewerState: { activity: "clinical_shift_debrief", committed: true },
          clinicalShiftContext: context,
        });
        if (!cancelled) {
          setReportCoach({
            tutorMessage: response.tutorMessage || response.feedback || "Your shift review is ready.",
            socraticQuestion: response.socraticQuestion,
            suggestedNextStep: response.suggestedNextStep,
          });
        }
      } catch (caught) {
        if (!cancelled) {
          setReportCoachError(readableApiError(caught, "The AI shift coach is temporarily unavailable."));
        }
      } finally {
        if (!cancelled) setReportCoachBusy(false);
      }
    })();
    return () => { cancelled = true; };
  }, [view, report?.tutorContext, report?.tutorContext?.contextId, report?.debrief?.aiPrompt]);

  useEffect(() => {
    let cancelled = false;
    setCoverageReady(false);
    setHandoffUnavailable("");
    clinicalApi.bankCoverage()
      .then(({ coverage, applicationCoverage }) => {
        if (cancelled) return;
        const source = handoffSubskill === "apply_in_context"
          ? Object.fromEntries(Object.entries(applicationCoverage ?? {}).flatMap(([concept, lanes]) => {
            const depth = lanes[lane];
            return depth ? [[concept, depth]] : [];
          }))
          : coverage;
        const available = Object.entries(source)
          .filter(([, row]) => row.items > 0 && row.distinctEcgs > 0)
          .map(([concept]) => concept);
        const resolution = handoffFocus ? resolveHandoffTarget(handoffFocus, available) : null;
        setHandoffResolution(resolution);
        if (handoffFocus && !resolution) {
          setHandoffUnavailable(`No eligible formative Clinical case in ${LANE_LABEL[lane]} currently checks ${conceptLabel(handoffFocus)}. An unrelated case will not be substituted.`);
        }
      })
      .catch(() => {
        if (!cancelled && handoffFocus) {
          setHandoffResolution(null);
          setHandoffUnavailable("Clinical case coverage could not be verified. This handoff is locked until the case bank is available again.");
        }
      })
      .finally(() => { if (!cancelled) setCoverageReady(true); });
    return () => { cancelled = true; };
  }, [handoffFocus, handoffSubskill, lane]);

  useEffect(() => {
    if (
      hydrating
      || preferencesLoading
      || !preferences
      || lengthChoiceSourceRef.current !== "untouched"
    ) return;
    lengthChoiceSourceRef.current = "preference";
    setLength(preferences.defaultSessionLength === 5 ? 5 : 10);
  }, [hydrating, preferencesLoading, preferences]);

  // clock
  const [remaining, setRemaining] = useState(0);
  const [running, setRunning] = useState(false);
  const [phaseReady, setPhaseReady] = useState(false);
  const clockEndRef = useRef<number>(0);
  const activationRef = useRef("");
  const waveformReadyRef = useRef({ key: "", current: false, prior: false });

  const item = current?.item ?? null;
  const isShift = mode === "shift";
  const sessionNoun = isShift ? "shift" : "learning set";
  const untimed = !isShift || !current?.clock || current.clock.untimed;

  const stopClock = useCallback(() => setRunning(false), []);

  const syncPhaseClock = useCallback((next: NextResult, clockPhase: "orient" | "decide") => {
    const clock = next.clock;
    if (!clock || clock.untimed) {
      setRunning(false);
      setRemaining(0);
      return;
    }
    const duration = clockPhase === "orient"
      ? (clock.orientSec ?? 0)
      : (clock.decideSec ?? 0);
    const deadlineValue = clockPhase === "orient" ? clock.orientDeadlineAt : clock.decideDeadlineAt;
    if (!deadlineValue) {
      clockEndRef.current = 0;
      setRemaining(duration);
      setRunning(false);
      return;
    }
    const deadline = Date.parse(deadlineValue);
    if (!Number.isFinite(deadline)) {
      setError("The case clock could not be started safely. Refresh before continuing this Clinical session.");
      setRunning(false);
      return;
    }
    clockEndRef.current = deadline;
    const secondsLeft = Math.max(0, (deadline - Date.now()) / 1000);
    setRemaining(secondsLeft);
    // An expired decision phase gets one immediate server submission tick; the
    // server independently decides whether it timed out.
    setRunning(secondsLeft > 0 || clockPhase === "decide");
  }, []);

  const loadNext = useCallback((next: NextResult) => {
    setNotice(null);
    setGrade(null);
    setTutorContext(null);
    setAnswer(next.firstLook ? {
      firstLookFinding: next.firstLook.firstLookFinding,
    } : {});
    setStepDraft(null);
    submissionRef.current = false;
    setRunning(false);
    setPhaseReady(Boolean(next.clock?.phaseStartedAt) || Boolean(next.clock?.untimed));
    setRemaining(0);
    clockEndRef.current = 0;
    activationRef.current = "";
    waveformReadyRef.current = { key: "", current: false, prior: false };
    setCompetencyReceipt(null);
    setAiViewerActions([]);
    setReviewActionStep(0);
    const nextPhase = next.contextRevealed ? "decide" : "orient";
    setPhase(nextPhase);
    setCurrent(next);
    syncPhaseClock(next, nextPhase);
  }, [syncPhaseClock]);

  useEffect(() => {
    const actions = grade?.viewerActions ?? [];
    if (phase !== "feedback" || actions.length === 0) {
      setReviewActionStep(0);
      return;
    }
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
      || document.documentElement.dataset.reduceMotion === "true";
    if (reduceMotion) {
      setReviewActionStep(actions.length);
      return;
    }
    setReviewActionStep(1);
    const id = window.setInterval(() => {
      setReviewActionStep((currentStep) => {
        if (currentStep >= actions.length) {
          window.clearInterval(id);
          return currentStep;
        }
        return currentStep + 1;
      });
    }, 900);
    return () => window.clearInterval(id);
  }, [grade?.caseId, grade?.viewerActions, phase, reviewPlaybackKey]);

  useEffect(() => {
    let cancelled = false;
    setHydrating(true);
    setError(null);
    setActiveShiftIntentConflict("");
    clinicalApi.active()
      .then((lifecycle) => {
        if (cancelled || !lifecycle.session) return;
        const params = new URLSearchParams(window.location.search);
        const requestedFocus = params.get("focus") ?? "";
        const requestedSubskill = params.get("subskill") ?? "";
        if (
          requestedFocus
          && (
            lifecycle.session.focusObjective !== requestedFocus
            || (requestedSubskill && lifecycle.session.focusSubskill !== requestedSubskill)
          )
        ) {
          const savedTarget = lifecycle.session.focusObjective
            ? conceptLabel(lifecycle.session.focusObjective)
            : "mixed clinical cases";
          setActiveShiftIntentConflict(
            `Your saved Clinical ${lifecycle.session.tier === "shift" ? "shift" : "set"} for ${savedTarget} was resumed unchanged. The recommended ${conceptLabel(requestedFocus)} application was not substituted into it. Finish or abandon the saved work, then open that recommendation again.`,
          );
        }
        setSession(lifecycle.session);
        setLane(lifecycle.session.lane);
        setMode(lifecycle.session.tier);
        lengthChoiceSourceRef.current = "restored";
        setLength(lifecycle.session.requestedLength ?? lifecycle.session.length);
        if (lifecycle.state === "report" && lifecycle.report) {
          setReport(lifecycle.report);
          setView("report");
          return;
        }
        if (lifecycle.current && ["orient", "decide", "feedback"].includes(lifecycle.state)) {
          loadNext(lifecycle.current);
          if (lifecycle.answer) setAnswer(lifecycle.answer);
          if (lifecycle.state === "feedback" && lifecycle.grade) {
            setGrade(lifecycle.grade);
            setTutorContext(lifecycle.tutorContext ?? null);
            setPhase("feedback");
            setRunning(false);
          }
          setView("runner");
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not check for an active Clinical shift.");
      })
      .finally(() => {
        if (!cancelled) setHydrating(false);
      });
    return () => { cancelled = true; };
  // AuthProvider remounts stateful pages on identity transition; this dependency
  // also documents that active discovery is learner-owned.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- loadNext intentionally hydrates only when learner identity changes.
  }, [identityKey, hydrationRetryKey]);

  useEffect(() => {
    if (phase !== "decide") return;
    const frame = window.requestAnimationFrame(() => {
      contextRef.current?.focus({ preventScroll: true });
      const rail = contextRef.current?.closest<HTMLElement>(".learning-response-rail");
      rail?.scrollTo({
        top: 0,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [phase]);

  const submit = useCallback(
    async () => {
      if (!session || !current?.itemId || !current.item || phase === "feedback" || submissionRef.current) return;
      submissionRef.current = true;
      stopClock();
      setBusy(true);
      setError(null);
      const payload: ClinicalAnswerPayload = {
        ...answer,
      };
      try {
        const { grade: g, tutorContext: groundedTutorContext } = await clinicalApi.answer(
          session.sessionId,
          current.itemId,
          payload,
        );
        setGrade(g);
        setTutorContext(groundedTutorContext);
        setCompetencyReceipt(null);
        const exactReceipts = g.competencyReceipts ?? [];
        if (handoffFocus && handoffSubskill && handoffResolution) {
          const receipt = exactReceipts.find((candidate) => (
            candidate.concept === handoffResolution.caseConcept && candidate.subskill === handoffSubskill
          ));
          if (!receipt) {
            setCompetencyReceipt(
              `Your clinical decision is saved. This case did not check ${skillLabel(handoffSubskill)} for ${conceptLabel(handoffResolution.caseConcept)}.`,
            );
          } else {
            setCompetencyReceipt(
              `Practice saved: ${conceptLabel(receipt.concept)} · ${skillLabel(receipt.subskill)}. This result will shape future Clinical case selection.`,
            );
          }
        } else if (exactReceipts.length) {
          const receipt = exactReceipts[0];
          setCompetencyReceipt(
            `Practice saved for ${exactReceipts.length} skill${exactReceipts.length === 1 ? "" : "s"}, including ${conceptLabel(receipt.concept)} · ${skillLabel(receipt.subskill)}.`,
          );
        }
        setPhase("feedback");
      } catch (e) {
        if (e instanceof Error && e.message.includes("clinical_item_expired")) {
          try {
            const replacement = await clinicalApi.next(session.sessionId);
            if (replacement.item) {
              loadNext(replacement);
              setNotice("That saved case expired after extended inactivity, so a different real ECG was loaded.");
            } else if (replacement.done) {
              setReport(await clinicalApi.report(session.sessionId));
              setView("report");
            } else {
              setError(replacement.reason || "That saved case expired and no replacement is available in this setting.");
            }
          } catch (replacementError) {
            setError(readableApiError(replacementError, "That saved case expired. Refresh to load a new case."));
          }
        } else {
          setError(readableApiError(e, "Your answer could not be checked. Try again."));
        }
      } finally {
        submissionRef.current = false;
        setBusy(false);
      }
    },
    [session, current, answer, phase, stopClock, handoffFocus, handoffSubskill, handoffResolution, loadNext],
  );

  // Orientation and decision are deliberately partitioned. Expiring the ECG-only
  // first-look clock must never submit an answer before clinical choices and a
  // confidence control are available. The fresh decision clock starts only after
  // the revealed response surface has painted and every required ECG is ready.
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      // `clockEndRef` stores the server's ISO deadline as Unix epoch milliseconds.
      // Keep the tick on the same clock domain: `performance.now()` is measured
      // from page navigation and would turn an epoch deadline into a multi-year
      // countdown that never expires.
      const rem = Math.max(0, (clockEndRef.current - Date.now()) / 1000);
      setRemaining(rem);
      if (rem <= 0) {
        setRunning(false);
        window.clearInterval(id);
        if (phase === "decide") void submit();
      }
    }, 200);
    return () => window.clearInterval(id);
  }, [running, submit, phase]);

  const onReady = useCallback(() => {
    // Viewer readiness owns only the transition from a clockless *timed* phase
    // to an active server clock. Learn sessions are untimed, and resumed/revealed
    // phases already carry their server start time. Posting /phase for either of
    // those states creates a race with context reveal: an in-flight orient request
    // can arrive after the server has moved to decide and correctly be rejected as
    // phase_not_ready. Keep a single request owner by never activating an already
    // ready phase.
    if (!session || !current?.itemId || phase === "feedback" || untimed || phaseReady) return;
    const activationKey = `${session.sessionId}:${current.itemId}:${phase}`;
    if (activationRef.current === activationKey) return;
    activationRef.current = activationKey;
    // This request is the durable readiness boundary: navigation/request time
    // never starts a Clinical assessment clock.
    void clinicalApi.activatePhase(session.sessionId, current.itemId, phase)
      .then((activated) => {
        if (activationRef.current !== activationKey) return;
        setCurrent(activated);
        setPhaseReady(true);
        syncPhaseClock(activated, phase);
      })
      .catch((e) => {
        if (activationRef.current !== activationKey) return;
        activationRef.current = "";
        setError(e instanceof Error ? e.message : "Could not activate the Clinical phase clock.");
      });
  }, [session, current, phase, untimed, phaseReady, syncPhaseClock]);

  const onWaveformReady = useCallback((which: "current" | "prior") => {
    if (!current?.itemId || !item) return;
    const readinessKey = current.itemId;
    if (waveformReadyRef.current.key !== readinessKey) {
      waveformReadyRef.current = { key: readinessKey, current: false, prior: false };
    }
    waveformReadyRef.current[which] = true;
    const needsPrior = Boolean(
      item.display_spec.mode === "stacked_twelve_lead" && item.prior_ecg_ref,
    );
    if (waveformReadyRef.current.current && (!needsPrior || waveformReadyRef.current.prior)) {
      onReady();
    }
  }, [current, item, onReady]);

  useEffect(() => {
    if (
      phase !== "decide"
      || phaseReady
      || untimed
      || !current?.itemId
      || !item
    ) return;
    const readiness = waveformReadyRef.current;
    const needsPrior = Boolean(
      item.display_spec.mode === "stacked_twelve_lead" && item.prior_ecg_ref,
    );
    if (
      readiness.key !== current.itemId
      || !readiness.current
      || (needsPrior && !readiness.prior)
    ) return;

    // The ECGs were already painted for first look. Wait through the revealed
    // context's next paint as a separate readiness boundary before activating
    // the server clock; comparison cases require both waveform callbacks above.
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => onReady());
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [current?.itemId, item, onReady, phase, phaseReady, untimed]);

  async function startShift() {
    if (handoffFocus && !coverageReady) {
      setError("Verifying the live Clinical case coverage for this handoff. Try again in a moment.");
      return;
    }
    if (handoffFocus && !handoffResolution) {
      setError(handoffUnavailable || "No eligible formative Clinical case currently supports this lesson handoff.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    setConfirmAbandon(false);
    try {
      const { session: s, next } = await clinicalApi.start({
        lane,
        tier: mode,
        length,
        focus: handoffResolution?.caseConcept,
        subskill: handoffSubskill ?? undefined,
      });
      if (!next.item) {
        setError(next.reason || "No compatible formative case is available in this setting.");
        setView("picker");
        return;
      }
      setSession(s);
      setReport(null);
      setReportCoach(null);
      setReportCoachError("");
      loadNext(next);
      setView("runner");
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not start the ${sessionNoun}.`);
    } finally {
      setBusy(false);
    }
  }

  async function commitFirstLook() {
    if (!session || !current?.itemId || !answer.firstLookFinding) return;
    setBusy(true);
    setError(null);
    try {
      const revealed = await clinicalApi.revealContext(session.sessionId, current.itemId, {
        firstLookFinding: answer.firstLookFinding,
      });
      setCurrent(revealed);
      setAnswer((currentAnswer) => ({
        ...currentAnswer,
        firstLookFinding: revealed.firstLook?.firstLookFinding ?? currentAnswer.firstLookFinding,
      }));
      setPhase("decide");
      setStepDraft(null);
      const decisionAlreadyStarted = Boolean(revealed.clock?.decideStartedAt);
      setPhaseReady(decisionAlreadyStarted || Boolean(revealed.clock?.untimed));
      activationRef.current = decisionAlreadyStarted
        ? `${session.sessionId}:${current.itemId}:decide`
        : "";
      syncPhaseClock(revealed, "decide");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reveal the clinical context.");
    } finally {
      setBusy(false);
    }
  }

  async function commitStepwiseStage() {
    const activeStep = current?.item?.stepwise_state?.active;
    if (!session || !current?.itemId || !activeStep || stepDraft == null || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await clinicalApi.commitStep(
        session.sessionId,
        current.itemId,
        activeStep.stepIndex,
        stepDraft,
      );
      setCurrent(next);
      setStepDraft(null);
    } catch (caught) {
      setError(readableApiError(caught, "That step could not be committed. Try again."));
    } finally {
      setBusy(false);
    }
  }

  async function goNext() {
    if (!session) return;
    setBusy(true);
    try {
      const next = await clinicalApi.next(session.sessionId);
      if (next.done) {
        const r = await clinicalApi.report(session.sessionId);
        setReport(r);
        setView("report");
      } else {
        loadNext(next);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not advance the ${sessionNoun}.`);
    } finally {
      setBusy(false);
    }
  }

  async function abandonShift() {
    if (!session || session.status !== "active" || busy) return;
    const destination = leaveAfterAbandon;
    const resumeClockOnFailure = running;
    stopClock();
    setBusy(true);
    setError(null);
    // Invalidate a viewer-readiness request that may still be in flight. Its
    // response must not reconstruct a presentation after the server retires it.
    activationRef.current = "abandoning";
    try {
      const abandoned = await clinicalApi.abandon(session.sessionId);
      if (abandoned.session?.status !== "abandoned" || abandoned.state !== "picker") {
        throw new Error(`We could not safely close this Clinical ${sessionNoun}. It remains open so no progress is lost.`);
      }
      setSession(null);
      setCurrent(null);
      setPhase("orient");
      setAnswer({});
      setGrade(null);
      setTutorContext(null);
      setReport(null);
      setRunning(false);
      setRemaining(0);
      setPhaseReady(false);
      clockEndRef.current = 0;
      activationRef.current = "";
      setCompetencyReceipt(null);
      setAiViewerActions([]);
      setConfirmAbandon(false);
      setNotice(
        `${isShift ? "Shift" : "Learning set"} closed. Completed cases stay in your history; the current unsubmitted case was discarded. Your setup choices are unchanged.`,
      );
      setView("picker");
      if (destination) window.location.assign(destination);
    } catch (e) {
      closeAbandonDialog();
      setError(e instanceof Error ? e.message : `Could not abandon this Clinical ${sessionNoun}.`);
      activationRef.current = "";
      if (resumeClockOnFailure && phase !== "feedback") setRunning(true);
    } finally {
      setBusy(false);
    }
  }

  async function retryClinicalItem() {
    if (!session || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await clinicalApi.next(session.sessionId);
      if (next.done) {
        const savedReport = await clinicalApi.report(session.sessionId);
        setReport(savedReport);
        setView("report");
      } else if (next.item) {
        loadNext(next);
        setView("runner");
      } else {
        setError(next.reason || "No compatible formative Clinical case is available.");
      }
    } catch (caught) {
      setError(readableApiError(caught, "The Clinical case could not be loaded. Try again."));
    } finally {
      setBusy(false);
    }
  }

  function backToClinicalSetup() {
    stopClock();
    setConfirmAbandon(false);
    setError(null);
    setView("picker");
  }

  // --- render ---------------------------------------------------------------
  if (view === "picker") {
    const startDisabled = hydrating
      || preferencesLoading
      || Boolean(handoffUnavailable)
      || Boolean(handoffFocus && !coverageReady);
    const setupStatus = hydrating
      ? `Checking for a saved ${sessionNoun}…`
      : preferencesLoading
        ? "Loading your setup…"
        : handoffFocus && !coverageReady
          ? "Finding a suitable case…"
          : `Preparing your ${sessionNoun}…`;
    return (
      <ClinicalSetupExperience
        lane={lane}
        onLaneChange={setLane}
        mode={mode}
        onModeChange={setMode}
        length={length}
        onLengthChange={(nextLength) => {
          lengthChoiceSourceRef.current = "user";
          setLength(nextLength);
        }}
        lengthOptions={LENGTHS}
        onStart={() => void startShift()}
        busy={busy || hydrating || preferencesLoading || Boolean(handoffFocus && !coverageReady)}
        disabled={startDisabled}
        startLabel={isShift ? "Start on-shift set" : "Begin learning set"}
        busyLabel={setupStatus}
        hero={{
          action: returnDestination ? {
            label: returnDestination.label,
            href: returnDestination.href,
            icon: <ArrowLeft size={16} aria-hidden="true" />,
            tone: "quiet",
          } : undefined,
        }}
        recommendation={{
          body: handoffResolution
            ? `Use a patient-care decision to strengthen ${conceptLabel(handoffResolution.caseConcept)}.`
            : "Your set will mix ECG interpretation, evidence tasks, and clinical decisions based on your recent learning.",
          focusLabel: handoffResolution ? conceptLabel(handoffResolution.caseConcept) : undefined,
          reason: handoffResolution
            ? `Recommended from your ${handoffSource}; the first case will honor that focus.`
            : "Cases stay varied so you practice transferring skills instead of memorizing one presentation.",
        }}
        launchDetail="The case mix adapts behind the scenes; no extra topic filter is needed."
        notices={(
          <>
            {activeShiftIntentConflict ? <div className="warning" role="alert">{activeShiftIntentConflict}</div> : null}
            {handoffUnavailable ? <div className="warning" role="alert">{handoffUnavailable}</div> : null}
            {notice ? <div className="selection-note" role="status">{notice}</div> : null}
            {error ? (
              <div className="warning mode-recovery-notice" role="alert">
                <span>{error}</span>
                <button className="button subtle small" type="button" onClick={() => setHydrationRetryKey((value) => value + 1)}>
                  <RefreshCw size={15} aria-hidden="true" /> Retry saved session check
                </button>
              </div>
            ) : null}
          </>
        )}
        footer={(
          <details className="clinical-content-note">
            <summary>About these learning cases</summary>
            <p>Patient stories are authored for education and paired with real deidentified ECGs. Case work guides future practice; scored mastery checks remain separate.</p>
          </details>
        )}
      />
    );
  }

  if (view === "report" && report) {
    const reportNoun = report.tier === "learn" ? "learning set" : "shift";
    const caseReviews = buildCaseReviewItems(report);
    const sbiFeedback = buildSBIFeedback(report, reportCoach);
    const priorityConcept = report.debrief?.priorityConcept;
    const conceptTopics = (report.debrief?.conceptEvidence ?? []).slice(0, 4).map((concept) => ({
      id: concept.concept,
      label: concept.label,
      status: concept.missedCount > concept.correctCount
        ? "priority" as const
        : concept.missedCount > 0
          ? "developing" as const
          : "strong" as const,
      statusLabel: concept.missedCount > concept.correctCount
        ? "Priority review"
        : concept.missedCount > 0
          ? "Keep developing"
          : "Strength demonstrated",
      progress: concept.caseCount > 0 ? Math.round((concept.correctCount / concept.caseCount) * 100) : undefined,
      href: report.debrief?.destinations.rapid?.concept === concept.concept
        ? report.debrief.destinations.rapid.href
        : undefined,
    }));
    return (
      <div className="clinical-shell">
        <ClinicalSetReviewExperience
          hero={{
            report,
            eyebrow: `${report.tier === "learn" ? "Learning set" : "Shift"} complete`,
            title: "Review the reasoning behind your decisions",
            summary: `You managed ${report.answered} patient case${report.answered === 1 ? "" : "s"} in ${LANE_LABEL[report.lane].toLowerCase()} practice. Revisit the ECG evidence, decisions, and explanations that matter most.`,
            supportingText: "These cases shape your personalized practice plan; independent ECG mastery is measured separately.",
            action: returnDestination ? {
              label: returnDestination.label,
              href: returnDestination.href,
              icon: <ArrowLeft size={16} aria-hidden="true" />,
              tone: "quiet",
            } : {
              label: "Dashboard",
              href: "/dashboard",
              icon: <LayoutDashboard size={16} aria-hidden="true" />,
              tone: "quiet",
            },
          }}
          summaryItems={buildClinicalDomainSummaries(report)}
          cases={{
            items: caseReviews,
            description: "Open a case to inspect its ECG, your response, and the teaching review without exposing answer keys in activity history.",
            action: report.reviewHref ? {
              label: "Review all ECGs and decisions",
              href: report.reviewHref,
              icon: <BookOpenCheck size={16} aria-hidden="true" />,
              tone: "secondary",
            } : undefined,
          }}
          nextSteps={report.debrief ? {
            summary: priorityConcept
              ? `${priorityConcept.label} is the most useful concept to strengthen next, based on this set and your independent practice history.`
              : "No single weakness dominated this set. Use another varied case set to keep transferring your reasoning.",
            topics: conceptTopics,
            action: report.debrief.destinations.clinical ? {
              label: `Apply ${report.debrief.destinations.clinical.label} in a new case`,
              href: report.debrief.destinations.clinical.href,
              icon: <ArrowRight size={15} aria-hidden="true" />,
              tone: "primary",
            } : undefined,
            secondaryAction: {
              label: "Open my study plan",
              href: report.debrief.destinations.adaptiveReview.href,
              tone: "quiet",
            },
          } : undefined}
          coaching={{
            feedback: sbiFeedback,
            personalizationNote: reportCoachBusy
              ? `Luna is connecting this ${reportNoun} with your recent learning history…`
              : reportCoach?.socraticQuestion
                ? `Reflection question: ${reportCoach.socraticQuestion}`
                : "Grounded in the completed cases and learning evidence available for this set.",
          }}
          notices={reportCoachError ? <div className="selection-note">{reportCoachError} Your saved review and next steps are still available.</div> : undefined}
          actions={(
            <>
              <button className="button primary" type="button" onClick={() => setView("picker")}>
                {report.tier === "learn" ? "Start another learning set" : "Start another shift"}
              </button>
              <Link className="button subtle" href="/dashboard"><LayoutDashboard size={16} aria-hidden="true" /> View learning dashboard</Link>
            </>
          )}
        />
        {!reportCoachBusy && report.tutorContext ? (
          <section className="panel pad clinical-set-coach-chat" aria-labelledby="clinical-set-coach-heading">
            <span className="eyebrow"><Sparkles size={15} aria-hidden="true" /> Ask Luna</span>
            <h2 id="clinical-set-coach-heading">Clarify, connect, or test what you learned</h2>
            <TutorChat
              mode="practice"
              roleLabel={`${report.tier === "learn" ? "Learning set" : "Shift"} review coach`}
              lessonId={report.tutorContext.contextId}
              clinicalShiftContext={report.tutorContext}
              openingPrompt="Ask for clarification, compare two decisions, connect the ECG evidence to patient care, or request a short transfer question."
              viewerState={{ activity: "clinical_shift_debrief", committed: true }}
              resetKey={report.tutorContext.contextId}
              collapsedByDefault
            />
          </section>
        ) : null}
      </div>
    );
  }

  if (!item || !session) {
    const loadingMessage = busy || hydrating ? "Loading the Clinical case…" : "No Clinical case is available to display.";
    return (
      <div className="clinical-shell clinical-empty-state">
        <section
          className={`panel pad${error ? " warning" : ""}`}
          role={error ? "alert" : "status"}
          aria-live={error ? "assertive" : "polite"}
          aria-busy={busy || hydrating}
        >
          <p className="eyebrow">Clinical decisions</p>
          <h1>{error ? "This case did not load" : "Preparing your case"}</h1>
          <p>{error ?? loadingMessage}</p>
          <div className="actions">
            {session ? (
              <button className="button primary" type="button" onClick={() => void retryClinicalItem()} disabled={busy || hydrating}>
                {busy ? "Retrying…" : "Retry"}
              </button>
            ) : null}
            <button className="button subtle" type="button" onClick={backToClinicalSetup}>Back to setup</button>
          </div>
        </section>
      </div>
    );
  }

  const labels = phaseLabels(item.situation);
  const phaseLabel = untimed ? null : phase === "orient" ? labels.orient : labels.decide;
  const total = phase === "orient" ? (current?.clock?.orientSec ?? 0) : (current?.clock?.decideSec ?? 0);
  const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0;
  const timedOut = phase === "feedback" && grade?.timedOut;
  const feedbackSucceeded = item.question_type === "matching"
    ? Boolean(grade?.matchingCorrect)
    : Boolean(grade && grade.score >= 0.6);
  const authoredReviewActions = grade?.viewerActions ?? [];
  const feedbackActions = phase === "feedback" && grade
    ? [...authoredReviewActions.slice(0, reviewActionStep), ...aiViewerActions]
    : [];
  const fillInTask = item.fill_in_task;
  const clinicalViewerTask: ViewerTaskSpec | undefined = phase !== "decide"
    ? undefined
    : (item.question_type === "click" || item.question_type === "spoterror") && item.click_roi_concept
      ? {
          mode: "point",
          prompt: item.prompt || "Mark the ECG evidence that supports your decision.",
          concept: item.click_roi_concept,
          allowedLeads: item.clickable_leads,
        }
      : item.question_type === "fillin" && fillInTask && ["ms", "bpm"].includes(fillInTask.unit)
        ? {
            mode: "caliper",
            prompt: `Use the calipers to estimate ${fillInTask.response_label.toLowerCase()}.`,
            measurement: measurementToolFor(fillInTask.response_label, fillInTask.unit),
          }
        : undefined;

  function captureClinicalEvidence(evidence: ViewerTaskEvidence) {
    if (evidence.mode === "point") {
      setAnswer((currentAnswer) => ({
        ...currentAnswer,
        click: {
          lead: evidence.point.lead,
          timeSec: evidence.point.timeSec,
          amplitudeMv: evidence.point.amplitudeMv,
        },
      }));
      return;
    }
    if (evidence.mode === "caliper" && fillInTask) {
      const measured = fillInTask.unit === "bpm"
        ? Math.round(60_000 / Math.max(1, evidence.valueMs))
        : Math.round(evidence.valueMs / fillInTask.step) * fillInTask.step;
      setAnswer((currentAnswer) => ({ ...currentAnswer, fillInValue: measured }));
    }
  }

  const responseLabel = phase === "orient"
    ? "Initial ECG interpretation"
    : phase === "decide"
      ? "Clinical context and decision"
      : "Clinical feedback";
  const activeEpisodeStage = item.question_type === "stepwise" ? item.stepwise_state?.active : null;
  const journeyStage = phase === "orient"
    ? "ecg"
    : phase === "feedback"
      ? "reassessment"
      : activeEpisodeStage?.stage_kind
        ?? (activeEpisodeStage ? "ecg" : "decision");
  const journey = buildClinicalJourney(journeyStage).map((stage) => (
    stage.status === "current" && activeEpisodeStage?.stage_title
      ? {
          ...stage,
          detail: [activeEpisodeStage.stage_title, activeEpisodeStage.elapsed_label].filter(Boolean).join(" · "),
        }
      : stage
  ));
  const patientVitals = [
    item.chips?.bp ? { label: "BP", value: item.chips.bp } : null,
    item.chips?.mental_status ? { label: "Status", value: humanLabel(item.chips.mental_status) } : null,
  ].filter((value): value is { label: string; value: string } => Boolean(value));
  const patientDetails = [
    item.chips?.setting ? { label: "Care setting", value: humanLabel(item.chips.setting) } : null,
    item.chips?.symptom && item.chips.symptom !== "none"
      ? { label: "Presenting concern", value: humanLabel(item.chips.symptom) }
      : null,
  ].filter((value): value is { label: string; value: string } => Boolean(value));
  const evidenceTimeline = authoredReviewActions.map((action, index) => ({
    id: `${item.item_id}-review-action-${index}`,
    title: viewerActionTitle(action),
    description: viewerActionDescription(action),
    status: index < reviewActionStep ? "complete" as const : index === reviewActionStep ? "current" as const : "upcoming" as const,
  }));

  return (
    <div className="clinical-shell clinical-shell-active">
      <LearningWorkspaceShell
        className={`clinical-runner${isShift ? " clinical-runner-timed" : ""}`}
        phase={phase}
        tutorResetKey={tutorContext?.contextId ?? item.item_id}
      >
        <SessionBar
          className="clinical-session-bar"
          tutorAvailable={phase === "feedback" && Boolean(tutorContext)}
          tutorLabel="Ask Luna"
        >
          <div className="clinical-session-meta">
            <strong>Case {current!.index + 1} of {current!.total}</strong>
            <span className="pill"><Stethoscope size={14} aria-hidden="true" /> {LANE_LABEL[item.situation]}</span>
          </div>
          {phase === "feedback" ? (
            <div className="clinical-clock complete" data-clock-phase="feedback">
              <CheckCircle2 size={14} aria-hidden="true" /> <span>Decision submitted</span>
            </div>
          ) : !untimed ? (
            <div className={`clinical-clock${phase === "decide" ? " decide" : ""}`} data-clock-phase={phase}>
              <Timer size={14} aria-hidden="true" />
              <span className="clinical-clock-label">{phaseLabel}</span>
              <progress className="clinical-clockbar" value={pct} max={100} aria-label={`${phaseLabel} time remaining`} />
              <span>{Math.ceil(remaining)}s</span>
            </div>
          ) : (
            <div className="clinical-clock untimed" data-clock-phase={phase}><Clock size={14} aria-hidden="true" /> <span>Learn — untimed</span></div>
          )}
          {returnDestination ? (
            <button
              className="button subtle small clinical-return-link"
              type="button"
              aria-haspopup="dialog"
              onClick={(event) => openAbandonDialog(event.currentTarget, returnDestination.href)}
              disabled={busy || confirmAbandon}
            >
              <ArrowLeft size={15} /> {returnDestination.label}
            </button>
          ) : null}
          {session?.status === "active" && !(phase === "feedback" && current!.index + 1 >= current!.total) ? (
            <button
              ref={abandonTriggerRef}
              className="button warn small clinical-abandon-button"
              type="button"
              aria-label={`Abandon ${sessionNoun}`}
              onClick={(event) => openAbandonDialog(event.currentTarget)}
              disabled={busy || confirmAbandon}
            >
              <span className="clinical-abandon-label">Exit {sessionNoun}</span>
              <span className="clinical-abandon-label-mobile" aria-hidden="true">Exit</span>
            </button>
          ) : null}
        </SessionBar>
        <ClinicalJourneyProgress stages={journey} label={`Case ${current!.index + 1} patient journey`} />

        <WorkspaceNotices>
          {confirmAbandon ? (
            <div className="clinical-abandon-modal-layer">
              <button className="clinical-abandon-backdrop" type="button" tabIndex={-1} aria-hidden="true" onClick={() => { if (!busy) closeAbandonDialog(); }} />
              <section
                ref={abandonDialogRef}
                className="panel pad clinical-abandon-confirmation"
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="clinical-abandon-title"
                aria-describedby="clinical-abandon-description"
                onKeyDown={(event) => {
                  if (event.key === "Escape" && !busy) {
                    event.preventDefault();
                    closeAbandonDialog();
                    return;
                  }
                  if (event.key !== "Tab") return;
                  const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')];
                  const first = focusable[0];
                  const last = focusable.at(-1);
                  if (!first || !last) return;
                  if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                  } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                  }
                }}
              >
                <h2 id="clinical-abandon-title">{leaveAfterAbandon ? `Leave this Clinical ${sessionNoun}?` : `Abandon this Clinical ${sessionNoun}?`}</h2>
                <p id="clinical-abandon-description" className="muted">
                  Completed case answers and saved progress stay in your learning history. Any current unsubmitted response,
                  revealed context, and timer state will be discarded, and this {session?.length ?? length}-case {sessionNoun} cannot be resumed.
                  Your setting, mode, and length choices will remain selected in setup.
                </p>
                <div className="actions">
                  <button ref={keepWorkingRef} className="button" type="button" onClick={closeAbandonDialog} disabled={busy}>
                    Keep working
                  </button>
                  <button className="button warn" type="button" onClick={() => void abandonShift()} disabled={busy}>
                    {leaveAfterAbandon ? `${returnDestination?.label ?? "Return"} and abandon ${sessionNoun}` : `Abandon ${sessionNoun} and change setup`}
                  </button>
                </div>
              </section>
            </div>
          ) : null}
          {activeShiftIntentConflict ? <div className="warning clinical-runner-error" role="alert">{activeShiftIntentConflict}</div> : null}
          {notice ? <div className="selection-note clinical-runner-notice" role="status">{notice}</div> : null}
          {error ? <div className="warning clinical-runner-error" role="alert">{error}</div> : null}
        </WorkspaceNotices>

        <WorkspaceBody className="clinical-active-workspace">
          <WaveformPane className="clinical-viewer-pane" label="Clinical ECG waveform">
            <ClinicalPatientSnapshot
              patientLabel={item.chips?.age != null ? `${item.chips.age}-year-old patient` : "Adult patient"}
              reasonForEcg={item.stem || "An ECG was requested to support the next clinical decision."}
              vitals={patientVitals}
              details={patientDetails}
              heading={phase === "orient" ? "Why this ECG was ordered" : "Patient presentation"}
              eyebrow={phase === "orient" ? "Presentation" : "Case context"}
            />
            {item.display_spec.mode === "stacked_twelve_lead" && item.prior_ecg_ref ? (
              <div className="clinical-stacked">
                <aside className="clinical-comparison-provenance" role="note" aria-label="ECG comparison provenance">
                  <strong>Authentic same-patient comparison</strong>
                  <span>These are time-ordered, real de-identified ECGs from the same patient. The surrounding clinical timeline is authored for learning.</span>
                </aside>
                <section className="clinical-comparison-study" aria-label="Current ECG">
                  <div className="clinical-strip-label">Current ECG</div>
                  <ECGViewer ecgRef={item.ecg_ref} waveformScope={{ kind: "clinical", sessionId: session.sessionId }} onReady={() => onWaveformReady("current")} actions={feedbackActions} toolbar="clinical" gradingMode="deferred" />
                </section>
                <section className="clinical-comparison-study" aria-label="Comparison ECG">
                  <div className="clinical-strip-label">Comparison ECG</div>
                  <ECGViewer ecgRef={item.prior_ecg_ref} waveformScope={{ kind: "clinical", sessionId: session.sessionId }} onReady={() => onWaveformReady("prior")} toolbar="clinical" gradingMode="deferred" />
                </section>
              </div>
            ) : (
              <ECGViewer
                ecgRef={item.ecg_ref}
                waveformScope={{ kind: "clinical", sessionId: session.sessionId }}
                onReady={() => onWaveformReady("current")}
                actions={feedbackActions}
                task={clinicalViewerTask}
                onTaskEvidence={clinicalViewerTask ? captureClinicalEvidence : undefined}
                gradingMode="deferred"
                toolbar="clinical"
                onCoordinate={
                  !clinicalViewerTask && (item.question_type === "click" || item.question_type === "spoterror")
                    ? (p: ECGPoint) => setAnswer((a) => ({ ...a, click: { lead: p.lead, timeSec: p.timeSec, amplitudeMv: p.amplitudeMv } }))
                    : undefined
                }
              />
            )}
          </WaveformPane>

          <ResponseRail
            className={`clinical-response-rail${phase === "orient" ? " clinical-first-look-dock" : ""}`}
            label={responseLabel}
            phase={phase}
          >
            {phase === "orient" ? (
              <section
                className="panel pad clinical-first-look"
                aria-labelledby="clinical-first-look-heading"
                aria-describedby="clinical-first-look-guidance"
              >
                <p className="eyebrow">ECG interpretation</p>
                <h2 id="clinical-first-look-heading">Record your initial ECG read</h2>
                <p id="clinical-first-look-guidance" className="muted clinical-first-look-guidance">
                  Use the ordering indication and the tracing together. Choose the broad pattern before the clinical decision is revealed.
                </p>
                <div className="clinical-first-look-fields">
                  <label htmlFor="clinical-first-look">Dominant ECG pattern</label>
                  <select
                    id="clinical-first-look"
                    aria-describedby="clinical-first-look-guidance"
                    value={answer.firstLookFinding ?? ""}
                    onChange={(event) => setAnswer((current) => ({ ...current, firstLookFinding: event.target.value || null }))}
                  >
                    <option value="">Choose the best broad category…</option>
                    {FIRST_LOOK_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </div>
                <button className="button primary clinical-first-look-submit" type="button" disabled={busy || (!untimed && !phaseReady) || !answer.firstLookFinding} onClick={() => void commitFirstLook()}>
                  {busy ? "Saving your interpretation…" : "Continue to the clinical decision"} <ArrowRight size={16} aria-hidden="true" />
                </button>
              </section>
            ) : phase === "decide" ? (
              <>
                {item.question_type === "spoterror" && item.machine_read ? (
                  <section className="panel pad clinical-machine">
                    <div className="clinical-strip-label">Machine read — click the wrong line</div>
                    {item.machine_read.map((ln) => (
                      <button
                        key={ln.id}
                        type="button"
                        className={`clinical-machine-line${answer.machineLineId === ln.id ? " selected" : ""}`}
                        aria-pressed={answer.machineLineId === ln.id}
                        onClick={() => setAnswer((a) => ({ ...a, machineLineId: ln.id }))}
                      >
                        {ln.text}
                      </button>
                    ))}
                  </section>
                ) : null}

                <section ref={contextRef} tabIndex={-1} className="panel pad clinical-question" aria-label="Clinical decision">
                  <p className="eyebrow">{questionTypeLabel(item.question_type)}</p>
                  <h2>{item.prompt}</h2>
                  {item.question_type === "stepwise" && item.stepwise_state ? (
                    <div
                      className="clinical-stepwise"
                      aria-label={[
                        ...item.stepwise_state.committed,
                        ...(item.stepwise_state.active ? [item.stepwise_state.active] : []),
                      ].some(hasEpisodeStageMetadata) ? "Evolving patient episode" : "Stepwise ECG interpretation"}
                    >
                      {item.stepwise_state.committed.map((step) => (
                        <div className="clinical-episode-stage" data-status="committed" key={`${item.item_id}-step-${step.stepIndex}`}>
                          <ClinicalEpisodeStageUpdate stage={step} stepNumber={step.stepIndex + 1} status="committed" />
                          <fieldset className="clinical-step-committed">
                            <legend>Step {step.stepIndex + 1} · {step.prompt}</legend>
                            <button type="button" className="selected" aria-pressed="true" disabled>{step.answerText}</button>
                            <p className="muted">Decision committed. This step is locked.</p>
                          </fieldset>
                        </div>
                      ))}
                      {item.stepwise_state.active ? (
                        <div className="clinical-episode-stage" data-status="active" key={`${item.item_id}-step-${item.stepwise_state.active.stepIndex}`}>
                          <ClinicalEpisodeStageUpdate
                            stage={item.stepwise_state.active}
                            stepNumber={item.stepwise_state.active.stepIndex + 1}
                            status="active"
                          />
                          <fieldset>
                            <legend>Step {item.stepwise_state.active.stepIndex + 1} of {item.stepwise_state.totalSteps} · {item.stepwise_state.active.prompt}</legend>
                            {item.stepwise_state.active.options.map((option, optionIndex) => (
                              <button
                                key={`${item.stepwise_state!.active!.stepIndex}-${optionIndex}`}
                                type="button"
                                className={stepDraft === optionIndex ? "selected" : ""}
                                aria-pressed={stepDraft === optionIndex}
                                onClick={() => setStepDraft(optionIndex)}
                              >{option.text}</button>
                            ))}
                            <button className="button primary clinical-step-commit" type="button" disabled={busy || stepDraft == null} onClick={() => void commitStepwiseStage()}>
                              {busy ? "Committing…" : item.stepwise_state.active.stepIndex + 1 === item.stepwise_state.totalSteps ? "Commit step and reveal clinical choices" : "Commit step and reveal next"}
                            </button>
                          </fieldset>
                        </div>
                      ) : (
                        <p className="selection-note" role="status">ECG sequence committed and locked. Now choose the clinical decision.</p>
                      )}
                    </div>
                  ) : null}
                  {item.question_type === "matching" && item.matching_task ? (
                    <fieldset className="clinical-matching" aria-describedby={`${item.item_id}-matching-help`}>
                      <legend>Evidence source map</legend>
                      <p id={`${item.item_id}-matching-help`} className="muted">
                        Assign each source once. Use the native menus with a mouse, touch, or keyboard.
                      </p>
                      <div className="clinical-matching-rows">
                        {item.matching_task.rows.map((row, index) => {
                          const selectId = `${item.item_id}-match-${row.id}`;
                          const selectedElsewhere = new Set(
                            Object.entries(answer.matches ?? {})
                              .filter(([rowId]) => rowId !== row.id)
                              .map(([, choiceId]) => choiceId),
                          );
                          return (
                            <div className="clinical-matching-row" key={row.id}>
                              <label htmlFor={selectId}>
                                <span>Clause {index + 1}</span>
                                <strong>{row.clause}</strong>
                              </label>
                              <select
                                id={selectId}
                                value={answer.matches?.[row.id] ?? ""}
                                onChange={(event) => {
                                  const choiceId = event.target.value;
                                  setAnswer((currentAnswer) => {
                                    const matches = { ...(currentAnswer.matches ?? {}) };
                                    if (choiceId) matches[row.id] = choiceId;
                                    else delete matches[row.id];
                                    return { ...currentAnswer, matches };
                                  });
                                }}
                              >
                                <option value="">Choose the strongest source…</option>
                                {item.matching_task!.choices.map((choice) => (
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
                  ) : item.question_type === "fillin" && item.fill_in_task ? (
                    <div className="field clinical-fill-in">
                      <label htmlFor={`${item.item_id}-fill-in`}>
                        {item.fill_in_task.response_label} ({item.fill_in_task.unit})
                      </label>
                      <input
                        id={`${item.item_id}-fill-in`}
                        type="number"
                        inputMode="numeric"
                        autoComplete="off"
                        min={item.fill_in_task.min_value}
                        max={item.fill_in_task.max_value}
                        step={item.fill_in_task.step}
                        value={answer.fillInValue ?? ""}
                        aria-describedby={`${item.item_id}-fill-in-help`}
                        onChange={(event) => {
                          const raw = event.target.value;
                          setAnswer((currentAnswer) => ({
                            ...currentAnswer,
                            fillInValue: raw === "" ? null : Number(raw),
                          }));
                        }}
                      />
                      <span id={`${item.item_id}-fill-in-help`} className="muted">
                        Use the ECG calipers or enter {item.fill_in_task.min_value}–{item.fill_in_task.max_value} {item.fill_in_task.unit}; nearest {item.fill_in_task.step} {item.fill_in_task.unit}.
                      </span>
                    </div>
                  ) : item.options && item.options.length ? (
                    <div className="clinical-options">
                      {item.options.map((opt, optionIndex) => (
                        <button
                          key={opt.id}
                          type="button"
                          className={`clinical-option${answer.selectedOptionId === opt.id ? " selected" : ""}`}
                          aria-pressed={answer.selectedOptionId === opt.id}
                          aria-label={`Option ${String.fromCharCode(65 + optionIndex)}: ${opt.text}`}
                          onClick={() => setAnswer((a) => ({ ...a, selectedOptionId: opt.id }))}
                        >
                          <span className="clinical-option-letter" aria-hidden="true">{String.fromCharCode(65 + optionIndex)}</span>
                          <span>{opt.text}</span>
                        </button>
                      ))}
                    </div>
                  ) : item.question_type === "click" || item.question_type === "spoterror" ? (
                    <p className="muted">
                      {answer.click ? `Selected ${answer.click.lead} at ${answer.click.timeSec.toFixed(2)}s.` : "Click the target on the trace above."}
                    </p>
                  ) : null}

                  <button className="button primary clinical-submit" type="button" disabled={busy || !canSubmit(item, answer)} onClick={() => void submit()}>
                    Commit decision
                  </button>
                </section>
              </>
            ) : grade ? (
              <ClinicalImmediateReview
                title={timedOut ? "Review the safest path" : "Review your decision"}
                tone={feedbackSucceeded ? "correct" : grade.safetyFlags?.length ? "safety" : "developing"}
                statusLabel={timedOut ? "Time ended" : feedbackSucceeded ? "Decision supported" : "Decision needs another pass"}
                learnerAnswer={<p>{clinicalAnswerSummary(item, answer)}</p>}
                recommendedAnswer={<p>{bestSupportedResponse(grade)}</p>}
                rationale={(
                  <>
                    <p>{grade.feedback}</p>
                    {grade.matchingResults?.length && item.matching_task ? (
                      <MatchingFeedback task={item.matching_task} results={grade.matchingResults} />
                    ) : null}
                    {grade.stepFeedback?.length ? (
                      <StepwiseFeedback results={grade.stepFeedback} />
                    ) : null}
                    {grade.firstLookAssessment ? <FirstLookFeedback assessment={grade.firstLookAssessment} /> : null}
                  </>
                )}
                supportingEvidence={[
                  ...grade.correctObjectives.map((objective) => `Supported: ${conceptLabel(objective)}`),
                  ...grade.missedObjectives.map((objective) => `Revisit: ${conceptLabel(objective)}`),
                ]}
                alternatives={!feedbackSucceeded && grade.answerClass ? [{
                  label: humanLabel(grade.answerClass),
                  explanation: answerClassExplanation(grade.answerClass),
                }] : []}
                safetyFlags={grade.safetyFlags?.map(humanLabel)}
                teachingPoints={grade.teachingPoints}
                coaching={(
                  <p>{tutorContext
                    ? "Ask Luna to connect the highlighted ECG evidence to the decision, explain the closest alternative, or give you a transfer question."
                    : "Your result is saved. The case coach is temporarily unavailable for this attempt."}</p>
                )}
                transferCheck={<p>Before continuing, name the single trace feature that most changed your next clinical action.</p>}
                notices={(
                  <>
                    {evidenceTimeline.length ? (
                      <div className="clinical-evidence-playback">
                        <ClinicalEvidenceTimeline steps={evidenceTimeline} heading="ECG evidence walkthrough" />
                        <button className="button subtle small" type="button" onClick={() => setReviewPlaybackKey((value) => value + 1)}>
                          <RotateCcw size={14} aria-hidden="true" /> Replay annotations
                        </button>
                      </div>
                    ) : null}
                    {competencyReceipt ? <p className="selection-note" role="status">{competencyReceipt}</p> : null}
                    <details className="clinical-assessment-details">
                      <summary>How this case was assessed</summary>
                      <p>This case informs future recommendations. Independent ECG mastery is checked separately on blinded tracings.</p>
                      {Object.keys(grade.axisScores ?? {}).length ? (
                        <div className="clinical-axes">
                          {Object.entries(grade.axisScores).map(([axis, score]) => (
                            <div key={axis} className="clinical-axis">
                              <span>{humanLabel(axis)}</span>
                              <progress className="clinical-axis-progress" value={score as number} max={1} aria-label={`${humanLabel(axis)} ${Math.round((score as number) * 100)} percent`} />
                            </div>
                          ))}
                        </div>
                      ) : null}
                      <p>{provenanceBadge(item.tracing_provenance)} · Patient context authored for learning.</p>
                    </details>
                  </>
                )}
                actions={(
                  <button className="button primary clinical-next" type="button" onClick={() => void goNext()} disabled={busy}>
                    {current!.index + 1 >= current!.total ? `Review ${sessionNoun}` : "Continue to next case"} <ArrowRight size={16} aria-hidden="true" />
                  </button>
                )}
              />
            ) : (
              <div className="panel pad clinical-feedback-loading" role="status" aria-live="polite" aria-busy="true">Loading saved feedback…</div>
            )}
          </ResponseRail>
        </WorkspaceBody>

        <TutorDrawer title="Ask Luna about this case">
          {tutorContext ? (
            <TutorChat
              mode="practice"
              roleLabel="Case tutor · after your decision"
              ecgRef={item.ecg_ref}
              lessonId={tutorContext.contextId}
              clinicalContext={tutorContext}
              openingPrompt="Ask why the ECG changed the decision, request a grounded highlight, or reason through the closest safe alternative."
              viewerState={{ activity: "clinical_case_debrief", committed: true }}
              onViewerActions={setAiViewerActions}
              resetKey={tutorContext.contextId}
            />
          ) : null}
        </TutorDrawer>
      </LearningWorkspaceShell>
    </div>
  );
}

const LEARNING_SUBSKILLS: LearningSubskill[] = [
  "recognize",
  "localize",
  "measure",
  "discriminate",
  "explain_mechanism",
  "synthesize",
  "apply_in_context",
  "calibrate_confidence",
];

function isLearningSubskill(value: string | null): value is LearningSubskill {
  return value != null && LEARNING_SUBSKILLS.includes(value as LearningSubskill);
}

function measurementToolFor(
  responseLabel: string,
  unit: NonNullable<NonNullable<NextResult["item"]>["fill_in_task"]>["unit"],
): "rr" | "pr" | "qrs" | "qt" | "custom" {
  if (unit === "bpm") return "rr";
  const label = responseLabel.toLowerCase();
  if (label.includes("qtc") || label.includes("qt")) return "qt";
  if (label.includes("qrs")) return "qrs";
  if (label.includes("pr")) return "pr";
  if (label.includes("rr")) return "rr";
  return "custom";
}

function canSubmit(item: NonNullable<NextResult["item"]>, answer: ClinicalAnswerPayload): boolean {
  if (item.question_type === "fillin") {
    const value = answer.fillInValue;
    const task = item.fill_in_task;
    return value != null
      && Number.isFinite(value)
      && Boolean(task)
      && value >= task!.min_value
      && value <= task!.max_value;
  }
  if (item.question_type === "matching") {
    const rows = item.matching_task?.rows ?? [];
    const choices = new Set(item.matching_task?.choices.map((choice) => choice.id) ?? []);
    const submitted = rows.map((row) => answer.matches?.[row.id]);
    return rows.length > 0
      && submitted.every((choiceId): choiceId is string => Boolean(choiceId && choices.has(choiceId)))
      && new Set(submitted).size === rows.length;
  }
  if (item.question_type === "click") return Boolean(answer.click);
  if (item.question_type === "spoterror") return Boolean(answer.click && answer.machineLineId);
  if (item.question_type === "stepwise") {
    const state = item.stepwise_state;
    const complete = Boolean(
      state
      && state.active === null
      && state.finalChoicesRevealed
      && state.committed.length === state.totalSteps,
    );
    return complete && Boolean(answer.selectedOptionId);
  }
  if (item.options?.length) return Boolean(answer.selectedOptionId);
  return true;
}

function firstLookCategoryLabel(value: string | null) {
  return FIRST_LOOK_OPTIONS.find(([candidate]) => candidate === value)?.[1] ?? "Not recorded";
}

function FirstLookFeedback({ assessment }: { assessment: NonNullable<ClinicalGrade["firstLookAssessment"]> }) {
  const interpretation = assessment.timedOut
    ? "The first-look window ended before this response was committed, so it is excluded from broad-category performance and confidence calibration."
    : assessment.agreement === true
    ? "Your broad interpretation matched the supported ECG category."
    : assessment.agreement === false
      ? "Your broad interpretation differed from the supported category. Re-check the first discriminating trace feature before the next decision."
      : "This broad interpretation could not be compared.";
  return (
    <section className="clinical-first-look-feedback" aria-labelledby="clinical-first-look-feedback-heading">
      <div>
        <p className="eyebrow">Initial ECG interpretation</p>
        <h3 id="clinical-first-look-feedback-heading">Your read after the ordering indication</h3>
      </div>
      <dl>
        <div><dt>Submitted broad category</dt><dd>{firstLookCategoryLabel(assessment.submittedCategory)}</dd></div>
        <div><dt>Expected broad category</dt><dd>{assessment.expectedCategories.map(firstLookCategoryLabel).join(" or ")}</dd></div>
        <div><dt>Comparison</dt><dd>{assessment.timedOut ? "Excluded — time ended" : assessment.agreement === true ? "Matched" : assessment.agreement === false ? "Did not match" : "Not assessable"}</dd></div>
      </dl>
      <p>{interpretation}</p>
      <p className="muted"><strong>Separate evidence:</strong> This is a formative broad-category check. It does not establish exact pathology recognition or change exact ECG mastery.</p>
    </section>
  );
}

function MatchingFeedback({
  task,
  results,
}: {
  task: NonNullable<NonNullable<NextResult["item"]>["matching_task"]>;
  results: NonNullable<ClinicalGrade["matchingResults"]>;
}) {
  const choices = new Map(task.choices.map((choice) => [choice.id, choice.label]));
  const rows = new Map(task.rows.map((row) => [row.id, row.clause]));
  return (
    <section className="clinical-matching-feedback" aria-labelledby="clinical-matching-feedback-heading">
      <h3 id="clinical-matching-feedback-heading">Evidence boundary review</h3>
      <ul>
        {results.map((result) => (
          <li className={result.correct ? "correct" : "incorrect"} key={result.rowId}>
            <strong>{rows.get(result.rowId) ?? "Clause"}</strong>
            <span>{result.correct ? "Correct" : "Correct source"}: {choices.get(result.correctChoiceId) ?? result.correctChoiceId}</span>
            {!result.correct && result.submittedChoiceId ? (
              <span>Your source: {choices.get(result.submittedChoiceId) ?? result.submittedChoiceId}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function StepwiseFeedback({
  results,
}: {
  results: NonNullable<ClinicalGrade["stepFeedback"]>;
}) {
  return (
    <section className="clinical-step-feedback" aria-labelledby="clinical-step-feedback-heading">
      <div className="clinical-step-feedback-heading">
        <p className="eyebrow">Patient-course review</p>
        <h3 id="clinical-step-feedback-heading">Reason through each decision point</h3>
      </div>
      <ol>
        {results.map((result) => (
          <li className={result.correct ? "correct" : "developing"} key={`${result.stageIndex}-${result.stageTitle}`}>
            <div className="clinical-step-feedback-status">
              <span>{result.stageIndex + 1}</span>
              <div>
                <strong>{result.stageTitle}</strong>
                {result.elapsedLabel ? <small>{result.elapsedLabel}</small> : null}
              </div>
              <b>{result.correct ? "Supported" : result.timedOut ? "Not credited" : "Revisit"}</b>
            </div>
            <p className="clinical-step-feedback-prompt">{result.prompt}</p>
            <dl>
              <div>
                <dt>Your response</dt>
                <dd>{result.learnerAnswer}</dd>
              </div>
              {!result.correct ? (
                <div>
                  <dt>Best-supported response</dt>
                  <dd>{result.supportedAnswer}</dd>
                </div>
              ) : null}
            </dl>
            <p className="clinical-step-feedback-explanation">{result.explanation}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function questionTypeLabel(questionType: NonNullable<NextResult["item"]>["question_type"]): string {
  const labels = {
    triage: "Prioritize care",
    stepwise: "Stepwise decision",
    click: "Prove it on the ECG",
    spoterror: "Audit the machine read",
    fillin: "Measure from the ECG",
    matching: "Match evidence to meaning",
    oldnew: "Compare prior ECG",
    mcq: "Clinical decision",
  } as const;
  return labels[questionType];
}

function viewerActionTitle(action: ViewerAction): string {
  const labels: Record<ViewerAction["type"], string> = {
    zoom: "Focus the relevant interval",
    highlightLead: "Compare the key leads",
    highlightROI: "Inspect the supporting region",
    circleROI: "Locate the decisive feature",
    drawCaliper: "Check the measurement",
    showFiducial: "Mark the reference point",
    resetView: "Return to the full tracing",
  };
  return action.label || labels[action.type];
}

function viewerActionDescription(action: ViewerAction): string {
  const leads = action.leads?.length ? action.leads.join(", ") : action.lead;
  const interval = action.timeStart != null && action.timeEnd != null
    ? `${action.timeStart.toFixed(2)}–${action.timeEnd.toFixed(2)} seconds`
    : action.timeSec != null
      ? `${action.timeSec.toFixed(2)} seconds`
      : "the authored teaching region";
  if (action.type === "highlightLead") return leads ? `Compare ${leads} before returning to the whole ECG.` : "Compare the highlighted leads.";
  if (action.type === "resetView") return "Reassess the finding in the context of the complete 12-lead ECG.";
  return `${leads ? `In ${leads}, inspect` : "Inspect"} ${interval}.`;
}

function clinicalAnswerSummary(item: NonNullable<NextResult["item"]>, answer: ClinicalAnswerPayload): string {
  if (item.question_type === "fillin" && answer.fillInValue != null) {
    return `${answer.fillInValue} ${item.fill_in_task?.unit ?? ""}`.trim();
  }
  if (item.question_type === "matching" && item.matching_task) {
    const choices = new Map(item.matching_task.choices.map((choice) => [choice.id, choice.label]));
    return item.matching_task.rows
      .map((row) => `${row.clause}: ${choices.get(answer.matches?.[row.id] ?? "") ?? "No source selected"}`)
      .join("; ");
  }
  if (item.question_type === "spoterror") {
    const line = item.machine_read?.find((candidate) => candidate.id === answer.machineLineId)?.text;
    const point = answer.click ? `${answer.click.lead} at ${answer.click.timeSec.toFixed(2)} s` : null;
    return [line ? `Machine statement: ${line}` : null, point ? `ECG evidence: ${point}` : null].filter(Boolean).join(" · ") || "No response recorded";
  }
  if (item.question_type === "click" && answer.click) return `${answer.click.lead} at ${answer.click.timeSec.toFixed(2)} seconds`;
  const selected = item.options?.find((option) => option.id === answer.selectedOptionId)?.text;
  return selected ?? (answer.timedOut ? "No response before time ended" : "No response recorded");
}

function bestSupportedResponse(grade: ClinicalGrade): string {
  if (grade.supportedAnswer) return grade.supportedAnswer;
  if (grade.teachingPoints.length) return grade.teachingPoints[0];
  if (grade.correctObjectives.length) {
    return `A response supported by ${grade.correctObjectives.map(conceptLabel).join(", ")} and the highlighted ECG evidence.`;
  }
  return "Use the highlighted ECG evidence and the case rationale to choose the safest supported action.";
}

function answerClassExplanation(answerClass: string): string {
  const explanations: Record<string, string> = {
    missing_required_safety_action: "The response did not include a time-sensitive action needed to keep the patient safe.",
    unsafe_choice: "The response could expose the patient to avoidable harm before the ECG finding is addressed.",
    under_triage: "The response does not match the urgency supported by the presentation and ECG.",
    over_triage: "The response escalates beyond what the available presentation and ECG evidence support.",
    incomplete: "Part of the reasoning was supported, but the response did not fully address the clinical decision.",
  };
  return explanations[answerClass] ?? "Compare this response with the supported ECG evidence and the patient-care consequence described above.";
}

function buildCaseReviewItems(report: ShiftReport): ClinicalCaseReviewItem[] {
  return (report.caseReviews ?? []).map((review) => ({
    id: `${report.reviewSessionRef ?? report.sessionId}-${review.attemptIndex}`,
    index: review.attemptIndex,
    title: review.title,
    context: [review.situation ? humanLabel(review.situation) : null, review.questionType ? humanLabel(review.questionType) : null]
      .filter(Boolean)
      .join(" · "),
    tags: review.objectiveLabels.slice(0, 3),
    outcome: review.correct ? "appropriate" : review.score >= 0.6 ? "developing" : "attention",
    outcomeLabel: review.correct ? "Supported decision" : review.score >= 0.6 ? "Partly supported" : "Review needed",
    href: review.reviewAvailable ? (review.reviewHref ?? review.replayHref) : undefined,
  }));
}

function buildSBIFeedback(
  report: ShiftReport,
  reportCoach: { tutorMessage: string; socraticQuestion?: string | null; suggestedNextStep?: string | null } | null,
): ClinicalSBIFeedback {
  const priority = report.debrief?.priorityConcept;
  const safety = report.performanceDomains?.safety;
  const decisionScore = report.performanceDomains?.clinicalApplicationDecision.score ?? report.accuracy;
  const situation = `Across ${report.answered} completed ${LANE_LABEL[report.lane].toLowerCase()} case${report.answered === 1 ? "" : "s"}, you interpreted the ECG and committed a patient-care decision.`;
  const behavior = priority
    ? `For ${priority.label}, you made ${priority.correctCount} supported decision${priority.correctCount === 1 ? "" : "s"} and had ${priority.missedCount} decision${priority.missedCount === 1 ? "" : "s"} that needed revision.`
    : `Your supported clinical-decision rate was ${Math.round(decisionScore * 100)}% across a varied case mix.`;
  const impact = safety?.flagged
    ? `${safety.flagged} decision${safety.flagged === 1 ? "" : "s"} carried a safety signal, so recognizing the trace must be linked more consistently to the next protective action.`
    : "Your decisions did not trigger a recorded safety concern; preserving the link between ECG evidence and action will help that reasoning transfer to less familiar presentations.";
  const nextStep = reportCoach?.suggestedNextStep
    ?? report.debrief?.nextCaseProposal?.reason
    ?? (priority
      ? `Practice one more varied case involving ${priority.label}, naming the decisive ECG feature before selecting the action.`
      : "Complete another varied clinical set and name the ECG evidence that changes each management decision.");
  const generated = reportCoach?.tutorMessage.match(
    /^\s*Situation:\s*(.+?)\s+Behavior:\s*(.+?)\s+Impact:\s*(.+?)\s+Next step:\s*(.+)\s*$/is,
  );
  if (!generated) return { situation, behavior, impact, nextStep };
  return {
    situation: generated[1].trim(),
    behavior: generated[2].trim(),
    impact: generated[3].trim(),
    nextStep: reportCoach?.suggestedNextStep?.trim() || generated[4].trim(),
  };
}
