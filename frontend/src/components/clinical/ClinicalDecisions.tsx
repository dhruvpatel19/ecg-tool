"use client";

import { Activity, ArrowLeft, ArrowRight, CheckCircle2, Clock, GitBranch, HeartPulse, RefreshCw, ShieldCheck, Sparkles, Stethoscope, Timer } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
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
} from "@/lib/clinical";
import { PinnedRhythmStrip } from "./PinnedRhythmStrip";
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
  const [busy, setBusy] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [returnTo, setReturnTo] = useState("");
  const [handoffFocus, setHandoffFocus] = useState("");
  const [handoffSubskill, setHandoffSubskill] = useState<LearningSubskill | null>(null);
  const [competencyReceipt, setCompetencyReceipt] = useState<string | null>(null);
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [handoffUnavailable, setHandoffUnavailable] = useState("");
  const [coverageReady, setCoverageReady] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<{ clinicianReviewed: boolean; label: string }>({
    clinicianReviewed: false,
    label: "pending_named_clinician_signoff",
  });
  const [aiViewerActions, setAiViewerActions] = useState<ViewerAction[]>([]);
  const contextRef = useRef<HTMLDivElement | null>(null);
  const submissionRef = useRef(false);
  const abandonTriggerRef = useRef<HTMLButtonElement | null>(null);
  const abandonDialogRef = useRef<HTMLElement | null>(null);
  const keepWorkingRef = useRef<HTMLButtonElement | null>(null);
  const lengthChoiceSourceRef = useRef<"untouched" | "preference" | "explicit" | "restored" | "user">("untouched");
  const returnDestination = parseLearningReturn(returnTo, CLINICAL_RETURN_SURFACES);
  const handoffSource = returnDestination?.surface === "study_plan"
    ? "study plan"
    : returnDestination?.surface === "lesson" ? "lesson" : "selected focus";

  const closeAbandonDialog = useCallback(() => {
    setConfirmAbandon(false);
    window.requestAnimationFrame(() => abandonTriggerRef.current?.focus());
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
      .then(({ coverage, applicationCoverage, clinicianReviewed, reviewStatus: liveReviewStatus }) => {
        if (cancelled) return;
        setReviewStatus({ clinicianReviewed, label: liveReviewStatus });
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
      firstLookConfidence: next.firstLook.firstLookConfidence,
    } : {});
    setStepDraft(null);
    submissionRef.current = false;
    setRunning(false);
    setPhaseReady(Boolean(next.clock?.phaseStartedAt) || Boolean(next.clock?.untimed));
    setRemaining(0);
    clockEndRef.current = 0;
    activationRef.current = "";
    setCompetencyReceipt(null);
    setAiViewerActions([]);
    const nextPhase = next.contextRevealed ? "decide" : "orient";
    setPhase(nextPhase);
    setCurrent(next);
    syncPhaseClock(next, nextPhase);
  }, [syncPhaseClock]);

  useEffect(() => {
    let cancelled = false;
    setHydrating(true);
    setError(null);
    clinicalApi.active()
      .then((lifecycle) => {
        if (cancelled || !lifecycle.session) return;
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
              `Practice saved: ${conceptLabel(receipt.concept)} · ${skillLabel(receipt.subskill)}. This case will shape what is recommended next.`,
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
  // confidence control are available; revealing context starts a fresh decision clock.
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
    if (!session || !current?.itemId || !answer.firstLookFinding || !answer.firstLookConfidence) return;
    setBusy(true);
    setError(null);
    try {
      const revealed = await clinicalApi.revealContext(session.sessionId, current.itemId, {
        firstLookFinding: answer.firstLookFinding,
        firstLookConfidence: answer.firstLookConfidence,
      });
      setCurrent(revealed);
      setAnswer((currentAnswer) => ({
        ...currentAnswer,
        firstLookFinding: revealed.firstLook?.firstLookFinding ?? currentAnswer.firstLookFinding,
        firstLookConfidence: revealed.firstLook?.firstLookConfidence ?? currentAnswer.firstLookConfidence,
      }));
      setPhase("decide");
      setStepDraft(null);
      setPhaseReady(true);
      activationRef.current = `${session.sessionId}:${current.itemId}:decide`;
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
    return (
      <div className="clinical-shell">
        <header className="page-header">
          <div>
            <span className="eyebrow"><Stethoscope size={15} aria-hidden="true" /> Clinical decisions</span>
            <h1>Use the ECG to make<br />the next decision.</h1>
            <p className="muted">
              Situation-framed cases where the ECG changes triage, medication safety, disposition, or follow-up.
              Every labeled tracing is real; the patient context is authored and clearly disclosed.
            </p>
          </div>
          {returnDestination ? <Link className="button subtle" href={returnDestination.href}><ArrowLeft size={16} /> {returnDestination.label}</Link> : null}
        </header>
        {handoffFocus ? (
          <div className="selection-note" style={{ marginBottom: 14 }}>
            From your {handoffSource}: apply <strong>{handoffFocus ? conceptLabel(handoffFocus) : "the current skill"}</strong>
            {handoffSubskill ? <> by practicing <strong>{skillLabel(handoffSubskill)}</strong></> : null} in a patient-care decision.
            {handoffResolution ? <> The first case focuses on <strong>{conceptLabel(handoffResolution.caseConcept)}</strong>.</> : null} Your ECG read and clinical decision are tracked separately.
          </div>
        ) : null}
        {handoffUnavailable ? <div className="warning" role="alert" style={{ marginBottom: 14 }}>{handoffUnavailable}</div> : null}
        {!reviewStatus.clinicianReviewed ? (
          <div className="selection-note" role="status" style={{ marginBottom: 14 }}>
            <strong>Supervised formative prototype:</strong> these cases passed automated provenance and grading checks, but named clinician sign-off is still pending. They do not award independent clinical mastery.
          </div>
        ) : null}
        {notice ? <div className="selection-note" role="status" style={{ marginBottom: 14 }}>{notice}</div> : null}
        {error ? (
          <div className="warning mode-recovery-notice" role="alert">
            <span>{error}</span>
            <button className="button subtle small" type="button" onClick={() => setHydrationRetryKey((value) => value + 1)}>
              <RefreshCw size={15} aria-hidden="true" /> Retry saved session check
            </button>
          </div>
        ) : null}
        <section className="panel pad clinical-picker">
          <div className="field">
            <span className="field-label" id="clinical-setting-label">Setting</span>
            <div className="segmented" role="group" aria-labelledby="clinical-setting-label">
              {LANES.map((l) => (
                <button key={l} type="button" className={l === lane ? "active" : ""} aria-pressed={l === lane} onClick={() => setLane(l)}>
                  {LANE_LABEL[l]}
                </button>
              ))}
            </div>
            <p className="muted clinical-data-boundary">Critical-care practice will open only after validated acute-rhythm ECGs are connected.</p>
          </div>
          <div className="field">
            <span className="field-label" id="clinical-mode-label">Mode</span>
            <div className="segmented" role="group" aria-labelledby="clinical-mode-label">
              <button type="button" className={mode === "learn" ? "active" : ""} aria-pressed={mode === "learn"} onClick={() => setMode("learn")}>
                Learn (untimed)
              </button>
              <button type="button" className={mode === "shift" ? "active" : ""} aria-pressed={mode === "shift"} onClick={() => setMode("shift")}>
                Shift (timed)
              </button>
            </div>
          </div>
          <div className="field">
            <span className="field-label" id="clinical-length-label">Length</span>
            <div className="segmented" role="group" aria-labelledby="clinical-length-label">
              {LENGTHS.map((n) => (
                <button key={n} type="button" className={n === length ? "active" : ""} aria-pressed={n === length} onClick={() => {
                  lengthChoiceSourceRef.current = "user";
                  setLength(n);
                }}>
                  {n} cases
                </button>
              ))}
            </div>
          </div>
          <button className="button primary" type="button" onClick={() => void startShift()} disabled={busy || hydrating || preferencesLoading || Boolean(handoffUnavailable) || Boolean(handoffFocus && !coverageReady)}>
            <Activity size={16} aria-hidden="true" /> {hydrating ? `Checking for a saved ${sessionNoun}…` : preferencesLoading ? "Loading your setup…" : handoffFocus && !coverageReady ? "Finding a suitable case…" : busy ? `Starting ${sessionNoun}…` : isShift ? "Start shift" : "Start learning set"} <ArrowRight size={16} aria-hidden="true" />
          </button>
          <p className="clinical-authorship-note"><ShieldCheck size={14} aria-hidden="true" /> Authored patient context · ECG source shown on every case · educational use only</p>
        </section>
      </div>
    );
  }

  if (view === "report" && report) {
    const domains = report.performanceDomains;
    const reportNoun = report.tier === "learn" ? "learning set" : "shift";
    return (
      <div className="clinical-shell">
        <header className="page-header">
          <div>
            <span className="eyebrow"><CheckCircle2 size={15} aria-hidden="true" /> {report.tier === "learn" ? "Learning set" : "Shift"} complete</span>
            <h1>{LANE_LABEL[report.lane]} · {report.tier === "learn" ? "Learn" : "Shift"}</h1>
          </div>
          {returnDestination ? <Link className="button subtle" href={returnDestination.href}><ArrowLeft size={16} /> {returnDestination.label}</Link> : null}
        </header>
        <section className="panel pad clinical-report">
          <div className="clinical-metric"><strong>{Math.round(report.accuracy * 100)}%</strong><span>accuracy</span></div>
          <div className="clinical-metric"><strong>{report.bestStreak}</strong><span>best streak</span></div>
          <div className="clinical-metric"><strong>{report.answered}/{report.length}</strong><span>answered</span></div>
          <div className="clinical-metric"><strong>{report.avgDecideMs != null ? `${(report.avgDecideMs / 1000).toFixed(1)}s` : "—"}</strong><span>avg decision</span></div>
          <div className="clinical-metric wide"><strong>{report.calibrationLabel}</strong><span>confidence match</span></div>
        </section>
        {domains ? (
          <section className="clinical-domain-report" aria-labelledby="clinical-domain-report-heading">
            <div className="clinical-domain-report-heading">
              <p className="eyebrow">Four separate signals</p>
              <h2 id="clinical-domain-report-heading">What this {reportNoun} actually checked</h2>
              <p className="muted">Clinical cases remain formative. Exact ECG pathology mastery changes only in an eligible mixed ECG check.</p>
            </div>
            <article className="panel pad clinical-domain-card">
              <h3>ECG recognition / first look</h3>
              <strong>{formatReportScore(domains.ecgRecognitionFirstLook.broadCategory.score)}</strong>
              <p>{domains.ecgRecognitionFirstLook.broadCategory.matched}/{domains.ecgRecognitionFirstLook.broadCategory.assessed} broad categories matched before context.</p>
              {Object.entries(domains.ecgRecognitionFirstLook.traceAxes).map(([axis, row]) => (
                <small key={axis}>{humanLabel(axis)}: {formatReportScore(row.score)} across {row.assessed} check{row.assessed === 1 ? "" : "s"}</small>
              ))}
              <small>Broad-category agreement is not exact pathology mastery.</small>
            </article>
            <article className="panel pad clinical-domain-card">
              <h3>Clinical application / decision</h3>
              <strong>{formatReportScore(domains.clinicalApplicationDecision.score)}</strong>
              <p>{domains.clinicalApplicationDecision.assessed} case decision{domains.clinicalApplicationDecision.assessed === 1 ? "" : "s"} assessed.</p>
              <small>Patient-care choices are tracked separately from recognizing the tracing.</small>
            </article>
            <article className="panel pad clinical-domain-card">
              <h3>Safety</h3>
              <strong>{domains.safety.safe}/{domains.safety.assessed}</strong>
              <p>safe decision{domains.safety.assessed === 1 ? "" : "s"} · {domains.safety.flagged} flagged · {domains.safety.unsafeChoices} unsafe choice{domains.safety.unsafeChoices === 1 ? "" : "s"}</p>
              <small>Safety reflects required actions and unsafe or under-triaged choices.</small>
            </article>
            <article className="panel pad clinical-domain-card">
              <h3>Confidence calibration</h3>
              <strong>{formatReportScore(domains.confidenceCalibration.score)}</strong>
              <p>{domains.confidenceCalibration.label}</p>
              <small>{domains.confidenceCalibration.highConfidenceMismatches} high-confidence first-look mismatch{domains.confidenceCalibration.highConfidenceMismatches === 1 ? "" : "es"}.</small>
            </article>
          </section>
        ) : null}
        {report.debrief ? (
          <section className="panel pad" aria-labelledby="clinical-shift-coach-heading">
            <span className="eyebrow"><Sparkles size={15} aria-hidden="true" /> AI reflection grounded in this {reportNoun}</span>
            <h2 id="clinical-shift-coach-heading">Choose the next useful move</h2>
            {reportCoachBusy ? <p className="muted" aria-live="polite">Reviewing this {reportNoun}…</p> : null}
            {reportCoach ? (
              <div aria-live="polite">
                <p>{reportCoach.tutorMessage}</p>
                {reportCoach.socraticQuestion ? <p><strong>Think next:</strong> {reportCoach.socraticQuestion}</p> : null}
              </div>
            ) : reportCoachError ? (
              <p className="selection-note">{reportCoachError} Your saved summary and next steps remain available below.</p>
            ) : null}
            {report.debrief.crossConceptBridge ? (
              <div className="selection-note">
                <GitBranch size={16} aria-hidden="true" />{" "}
                <strong>Connect these skills:</strong> {report.debrief.crossConceptBridge.prompt}
              </div>
            ) : (
              <p className="muted">Only one ECG finding appeared in this {reportNoun}. Complete another case before connecting it to a second pattern.</p>
            )}
            {report.debrief.nextCaseProposal ? (
              <p className="muted">
                <strong>Why this case next:</strong> A different real ECG is available in this setting to practice {report.debrief.nextCaseProposal.label}.
              </p>
            ) : null}
            <div className="actions">
              {report.debrief.destinations.clinical ? (
                <Link className="button primary" href={report.debrief.destinations.clinical.href}>
                  Apply {report.debrief.destinations.clinical.label} in a new case <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : null}
              {report.debrief.destinations.rapid ? (
                <Link className="button" href={report.debrief.destinations.rapid.href}>
                  Recheck the ECG pattern <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : null}
              <Link className="button subtle" href={report.debrief.destinations.adaptiveReview.href}>Open my study plan</Link>
            </div>
            {!reportCoachBusy && report.tutorContext ? (
              <TutorChat
                mode="practice"
                roleLabel={`${report.tier === "learn" ? "Learning set" : "Shift"} debrief coach`}
                lessonId={report.tutorContext.contextId}
                clinicalShiftContext={report.tutorContext}
                openingPrompt="Ask about the recurring reasoning pattern, the supported concept bridge, or why the proposed real-ECG case comes next."
                viewerState={{ activity: "clinical_shift_debrief", committed: true }}
                resetKey={report.tutorContext.contextId}
                collapsedByDefault
              />
            ) : null}
          </section>
        ) : null}
        <div className="actions">
          <button className="button primary" type="button" onClick={() => setView("picker")}>{report.tier === "learn" ? "New learning set" : "New shift"}</button>
          {returnDestination ? <Link className="button subtle" href={returnDestination.href}><ArrowLeft size={16} /> {returnDestination.label}</Link> : null}
        </div>
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
  const feedbackActions = phase === "feedback" && grade ? [...(grade.viewerActions ?? []), ...aiViewerActions] : [];
  const clinicalViewerTask: ViewerTaskSpec | undefined = phase === "decide"
    && (item.question_type === "click" || item.question_type === "spoterror")
    && item.click_roi_concept
    ? {
        mode: "point",
        prompt: item.prompt || "Mark the ECG evidence that supports your decision.",
        concept: item.click_roi_concept,
        allowedLeads: item.clickable_leads,
      }
    : undefined;

  function captureClinicalPoint(evidence: ViewerTaskEvidence) {
    if (evidence.mode !== "point") return;
    setAnswer((currentAnswer) => ({
      ...currentAnswer,
      click: {
        lead: evidence.point.lead,
        timeSec: evidence.point.timeSec,
        amplitudeMv: evidence.point.amplitudeMv,
      },
    }));
  }

  const responseLabel = phase === "orient"
    ? "Clinical first look"
    : phase === "decide"
      ? "Clinical context and decision"
      : "Clinical feedback";

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
          tutorLabel="Open tutor"
        >
          <div className="clinical-session-meta">
            <span className="pill"><Stethoscope size={14} aria-hidden="true" /> {LANE_LABEL[item.situation]}</span>
            <span className="pill subtle">{questionTypeLabel(item.question_type)}</span>
            <span className="muted">Case {current!.index + 1} / {current!.total}</span>
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
          {returnDestination ? <Link className="button subtle small clinical-return-link" href={returnDestination.href}><ArrowLeft size={15} /> {returnDestination.label}</Link> : null}
          {session?.status === "active" && !(phase === "feedback" && current!.index + 1 >= current!.total) ? (
            <button
              ref={abandonTriggerRef}
              className="button warn small clinical-abandon-button"
              type="button"
              aria-label={`Abandon ${sessionNoun}`}
              onClick={() => setConfirmAbandon(true)}
              disabled={busy || confirmAbandon}
            >
              <span className="clinical-abandon-label">Abandon {sessionNoun}</span>
              <span className="clinical-abandon-label-mobile" aria-hidden="true">Exit</span>
            </button>
          ) : null}
        </SessionBar>

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
                <h2 id="clinical-abandon-title">Abandon this Clinical {sessionNoun}?</h2>
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
                    Abandon {sessionNoun} and change setup
                  </button>
                </div>
              </section>
            </div>
          ) : null}
          {notice ? <div className="selection-note clinical-runner-notice" role="status">{notice}</div> : null}
          {error ? <div className="warning clinical-runner-error" role="alert">{error}</div> : null}
        </WorkspaceNotices>

        <WorkspaceBody className="clinical-active-workspace">
          <WaveformPane className="clinical-viewer-pane" label="Clinical ECG waveform">
            {item.display_spec.mode === "stacked_twelve_lead" && item.prior_ecg_ref ? (
              <div className="clinical-stacked">
                <div><div className="clinical-strip-label">Today</div><ECGViewer ecgRef={item.ecg_ref} waveformScope={{ kind: "clinical", sessionId: session.sessionId }} onReady={onReady} actions={feedbackActions} gradingMode="deferred" /></div>
                <div><div className="clinical-strip-label">Prior</div><ECGViewer ecgRef={item.prior_ecg_ref} waveformScope={{ kind: "clinical", sessionId: session.sessionId }} toolbar="none" gradingMode="deferred" /></div>
              </div>
            ) : (
              <>
                <ECGViewer
                  ecgRef={item.ecg_ref}
                  waveformScope={{ kind: "clinical", sessionId: session.sessionId }}
                  onReady={onReady}
                  actions={feedbackActions}
                  task={clinicalViewerTask}
                  onTaskEvidence={clinicalViewerTask ? captureClinicalPoint : undefined}
                  gradingMode="deferred"
                  onCoordinate={
                    !clinicalViewerTask && (item.question_type === "click" || item.question_type === "spoterror")
                      ? (p: ECGPoint) => setAnswer((a) => ({ ...a, click: { lead: p.lead, timeSec: p.timeSec, amplitudeMv: p.amplitudeMv } }))
                      : undefined
                  }
                />
                {item.display_spec.mode === "twelve_lead_pinned_strip" ? (
                  <details className="clinical-rhythm-detail">
                    <summary>Magnify lead {item.display_spec.pinned_strip_lead ?? "II"} rhythm strip</summary>
                    <PinnedRhythmStrip ecgRef={item.ecg_ref} sessionId={session.sessionId} lead={item.display_spec.pinned_strip_lead ?? "II"} />
                  </details>
                ) : null}
              </>
            )}
          </WaveformPane>

          <ResponseRail
            className={`clinical-response-rail${phase === "orient" ? " clinical-first-look-dock" : ""}`}
            label={responseLabel}
            phase={phase}
          >
            {phase === "orient" ? (
              <>
                <div className="selection-note clinical-context-mask">
                  <strong>ECG first.</strong> The patient context stays hidden until you commit an initial read.
                </div>
                <section
                  className="panel pad clinical-first-look"
                  aria-labelledby="clinical-first-look-heading"
                  aria-describedby="clinical-first-look-guidance"
                >
                  <h2 id="clinical-first-look-heading">What is the dominant ECG pattern?</h2>
                  <p id="clinical-first-look-guidance" className="muted clinical-first-look-guidance">
                    This checks your ECG-only read before the patient story appears.
                  </p>
                  <div className="clinical-first-look-fields">
                    <label htmlFor="clinical-first-look">Dominant finding</label>
                    <select
                      id="clinical-first-look"
                      aria-describedby="clinical-first-look-guidance"
                      value={answer.firstLookFinding ?? ""}
                      onChange={(event) => setAnswer((current) => ({ ...current, firstLookFinding: event.target.value || null }))}
                    >
                      <option value="">Choose the best ECG-only category…</option>
                      {FIRST_LOOK_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                    </select>
                    <fieldset>
                      <legend>First-look confidence</legend>
                      {[{ value: 2, label: "Low" }, { value: 3, label: "Medium" }, { value: 5, label: "High" }].map((choice) => (
                        <button
                          key={choice.value}
                          type="button"
                          className={answer.firstLookConfidence === choice.value ? "active" : ""}
                          aria-pressed={answer.firstLookConfidence === choice.value}
                          onClick={() => setAnswer((current) => ({ ...current, firstLookConfidence: choice.value }))}
                        >
                          {choice.label}
                        </button>
                      ))}
                    </fieldset>
                  </div>
                  <button className="button primary clinical-first-look-submit" type="button" disabled={busy || (!untimed && !phaseReady) || !answer.firstLookFinding || !answer.firstLookConfidence} onClick={() => void commitFirstLook()}>
                    {busy ? "Saving first look…" : "Commit first look and reveal context"} <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </section>
              </>
            ) : phase === "decide" ? (
              <>
                <section ref={contextRef} tabIndex={-1} className="panel pad clinical-stem" aria-label="Clinical context and decision prompt">
                  <p>{item.stem}</p>
                  {item.chips ? (
                    <div className="clinical-chips">
                      {item.chips.age != null ? <span className="chip">{item.chips.age}y</span> : null}
                      {item.chips.bp ? <span className="chip">BP {item.chips.bp}</span> : null}
                      {item.chips.symptom && item.chips.symptom !== "none" ? <span className="chip">{item.chips.symptom.replace(/_/g, " ")}</span> : null}
                      {item.chips.mental_status ? <span className="chip">{item.chips.mental_status}</span> : null}
                    </div>
                  ) : null}
                </section>

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

                <section className="panel pad clinical-question">
                  <strong>{item.prompt}</strong>
                  {item.question_type === "stepwise" && item.stepwise_state ? (
                    <div className="clinical-stepwise" aria-label="Stepwise ECG interpretation">
                      {item.stepwise_state.committed.map((step) => (
                        <fieldset className="clinical-step-committed" key={`${item.item_id}-step-${step.stepIndex}`}>
                          <legend>Step {step.stepIndex + 1} · {step.prompt}</legend>
                          <button type="button" className="selected" aria-pressed="true" disabled>{step.answerText}</button>
                          <p className="muted" role="status">Decision committed. This step is locked.</p>
                        </fieldset>
                      ))}
                      {item.stepwise_state.active ? (
                        <fieldset key={`${item.item_id}-step-${item.stepwise_state.active.stepIndex}`}>
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
                        Enter {item.fill_in_task.min_value}–{item.fill_in_task.max_value} {item.fill_in_task.unit}; nearest {item.fill_in_task.step} {item.fill_in_task.unit}.
                      </span>
                    </div>
                  ) : item.options && item.options.length ? (
                    <div className="clinical-options">
                      {item.options.map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          className={`clinical-option${answer.selectedOptionId === opt.id ? " selected" : ""}`}
                          aria-pressed={answer.selectedOptionId === opt.id}
                          onClick={() => setAnswer((a) => ({ ...a, selectedOptionId: opt.id }))}
                        >
                          {opt.text}
                        </button>
                      ))}
                    </div>
                  ) : item.question_type === "click" || item.question_type === "spoterror" ? (
                    <p className="muted">
                      {answer.click ? `Selected ${answer.click.lead} at ${answer.click.timeSec.toFixed(2)}s.` : "Click the target on the trace above."}
                    </p>
                  ) : null}

                  {isShift && (item.options?.length || item.question_type === "spoterror" || item.question_type === "fillin" || item.question_type === "matching") ? (
                    <div className="clinical-confidence">
                      <span className="muted">Confidence</span>
                      {[
                        { v: 2, l: "Low" },
                        { v: 3, l: "Medium" },
                        { v: 5, l: "High" },
                      ].map((c) => (
                        <button
                          key={c.v}
                          type="button"
                          className={answer.confidence === c.v ? "active" : ""}
                          aria-pressed={answer.confidence === c.v}
                          onClick={() => setAnswer((a) => ({ ...a, confidence: c.v }))}
                        >
                          {c.l}
                        </button>
                      ))}
                    </div>
                  ) : null}

                  <button className="button primary clinical-submit" type="button" disabled={busy || !canSubmit(item, answer, isShift)} onClick={() => void submit()}>
                    Commit decision
                  </button>
                </section>
              </>
            ) : grade ? (
              <section className={`panel pad clinical-feedback ${feedbackSucceeded ? "ok" : "miss"}`}>
                <h2>
                  <HeartPulse size={18} aria-hidden="true" />{" "}
                  {timedOut
                    ? "Time"
                    : feedbackSucceeded
                      ? item.question_type === "matching" ? "Evidence sorted" : "Good decision"
                      : "Reconsider"} · {Math.round(grade.score * 100)}%
                  {grade.answerClass ? <span className="pill subtle">{grade.answerClass.replace(/_/g, " ")}</span> : null}
                </h2>
                <p>{grade.feedback}</p>
                {grade.matchingResults?.length && item.matching_task ? (
                  <MatchingFeedback task={item.matching_task} results={grade.matchingResults} />
                ) : null}
                {grade.firstLookAssessment ? <FirstLookFeedback assessment={grade.firstLookAssessment} /> : null}
                {grade.clinicalApplicationEvidence === "formative_only" ? (
                  <p className="selection-note">This case shapes your next recommendation. Mixed ECG checks update mastery separately.</p>
                ) : null}
                {grade.ecgRecognitionSuppressed ? (
                  <p className="selection-note">
                    The vignette revealed ECG clues, so this result records your clinical reasoning separately from ECG recognition.
                  </p>
                ) : null}
                {competencyReceipt ? <p className="selection-note" role="status">{competencyReceipt}</p> : null}
                {grade.safetyFlags?.length ? (
                  <p className="warning">Safety check: {grade.safetyFlags.map(humanLabel).join(" · ")}</p>
                ) : null}
                {Object.keys(grade.axisScores ?? {}).length ? (
                  <div className="clinical-axes">
                    {Object.entries(grade.axisScores).map(([axis, score]) => (
                      <div key={axis} className="clinical-axis">
                        <span>{humanLabel(axis)}</span>
                        <progress
                          className="clinical-axis-progress"
                          value={score as number}
                          max={1}
                          aria-label={`${humanLabel(axis)} ${Math.round((score as number) * 100)} percent`}
                        />
                      </div>
                    ))}
                  </div>
                ) : null}
                {grade.teachingPoints?.length ? <p className="muted">{grade.teachingPoints.join(" ")}</p> : null}
                {!tutorContext ? (
                  <p className="warning" role="status">
                    Your result is saved, but the AI tutor is unavailable for this attempt.
                  </p>
                ) : null}
                <button className="button primary clinical-next" type="button" onClick={() => void goNext()} disabled={busy}>
                  {current!.index + 1 >= current!.total ? `Finish ${sessionNoun}` : "Next case"} <ArrowRight size={16} aria-hidden="true" />
                </button>
              </section>
            ) : (
              <div className="panel pad clinical-feedback-loading" role="status" aria-live="polite" aria-busy="true">Loading saved feedback…</div>
            )}
          </ResponseRail>
        </WorkspaceBody>

        <DisclosureArea className="clinical-disclosure">
          <span className="clinical-provenance"><ShieldCheck size={14} aria-hidden="true" /> {provenanceBadge(item.tracing_provenance)}</span>
          <span className="pill subtle">Patient context authored for learning</span>
        </DisclosureArea>

        <TutorDrawer title="Case tutor">
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

function canSubmit(item: NonNullable<NextResult["item"]>, answer: ClinicalAnswerPayload, isShift: boolean): boolean {
  const needConfidence = isShift && (Boolean(item.options?.length) || item.question_type === "spoterror" || item.question_type === "fillin" || item.question_type === "matching");
  if (needConfidence && !answer.confidence) return false;
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

function confidenceLabel(value: number | null) {
  return value === 5 ? "High" : value === 3 ? "Medium" : value === 2 ? "Low" : "Not recorded";
}

function FirstLookFeedback({ assessment }: { assessment: NonNullable<ClinicalGrade["firstLookAssessment"]> }) {
  const calibration = assessment.agreement === true
    ? assessment.confidence === 5
      ? "Your high confidence matched the broad ECG category."
      : assessment.confidence === 2
        ? "The broad category matched; consider what trace feature would justify more confidence."
        : "Your confidence was proportionate to a matching broad category."
    : assessment.agreement === false
      ? assessment.confidence === 5
        ? "High-confidence mismatch: slow down and name the first discriminating feature before committing."
        : "The broad category did not match; use the trace-level feedback to recalibrate your next first look."
      : "This first look could not be compared.";
  return (
    <section className="clinical-first-look-feedback" aria-labelledby="clinical-first-look-feedback-heading">
      <div>
        <p className="eyebrow">ECG-only commitment</p>
        <h3 id="clinical-first-look-feedback-heading">Your first look, before the vignette</h3>
      </div>
      <dl>
        <div><dt>Submitted broad category</dt><dd>{firstLookCategoryLabel(assessment.submittedCategory)}</dd></div>
        <div><dt>Expected broad category</dt><dd>{assessment.expectedCategories.map(firstLookCategoryLabel).join(" or ")}</dd></div>
        <div><dt>Confidence</dt><dd>{confidenceLabel(assessment.confidence)}</dd></div>
        <div><dt>Calibration</dt><dd>{assessment.agreement === true ? "Matched" : assessment.agreement === false ? "Did not match" : "Not assessable"}</dd></div>
      </dl>
      <p>{calibration}</p>
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

function formatReportScore(score: number | null) {
  return score == null ? "Not assessed" : `${Math.round(score * 100)}%`;
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
