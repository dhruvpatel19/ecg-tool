"use client";

import { Activity, ArrowLeft, ArrowRight, CheckCircle2, Clock, HeartPulse, ShieldCheck, Stethoscope, Timer } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import type { ECGPoint } from "@/lib/coordinates";
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
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import type { ViewerAction, ViewerTaskEvidence, ViewerTaskSpec } from "@/lib/types";

type View = "picker" | "runner" | "report";
type Phase = "orient" | "decide" | "feedback";

const LANES: Lane[] = ["clinic", "ward", "ed"];
const LENGTHS = [5, 10];
const FIRST_LOOK_OPTIONS = [
  ["normal_or_no_dominant_abnormality", "Normal / no dominant abnormality"],
  ["rate_or_rhythm", "Rate or rhythm abnormality"],
  ["conduction_or_interval", "Conduction or interval abnormality"],
  ["st_t_or_ischemia", "ST–T / ischemia pattern"],
  ["chamber_or_voltage", "Chamber / voltage pattern"],
  ["uncertain", "Uncertain — need clinical context"],
] as const;

export function ClinicalDecisions() {
  const { identityKey } = useAuth();
  const [view, setView] = useState<View>("picker");
  const [lane, setLane] = useState<Lane>("clinic");
  const [mode, setMode] = useState<Mode>("shift");
  const [length, setLength] = useState(5);

  const [session, setSession] = useState<ShiftSession | null>(null);
  const [current, setCurrent] = useState<NextResult | null>(null);
  const [phase, setPhase] = useState<Phase>("orient");
  const [answer, setAnswer] = useState<ClinicalAnswerPayload>({});
  const [grade, setGrade] = useState<ClinicalGrade | null>(null);
  const [report, setReport] = useState<ShiftReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [returnTo, setReturnTo] = useState("");
  const [handoffFocus, setHandoffFocus] = useState("");
  const [handoffSubskill, setHandoffSubskill] = useState<LearningSubskill | null>(null);
  const [competencyReceipt, setCompetencyReceipt] = useState<string | null>(null);
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [handoffUnavailable, setHandoffUnavailable] = useState("");
  const [coverageReady, setCoverageReady] = useState(false);
  const [aiViewerActions, setAiViewerActions] = useState<ViewerAction[]>([]);
  const contextRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedReturn = params.get("returnTo") ?? "";
    if (requestedReturn.startsWith("/learn/")) setReturnTo(requestedReturn);
    const requestedFocus = params.get("focus") ?? "";
    setHandoffFocus(requestedFocus);
    const requestedSubskill = params.get("subskill");
    if (isLearningSubskill(requestedSubskill)) setHandoffSubskill(requestedSubskill);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setCoverageReady(false);
    setHandoffUnavailable("");
    clinicalApi.bankCoverage()
      .then(({ coverage }) => {
        if (cancelled) return;
        const available = Object.entries(coverage)
          .filter(([, row]) => row.items > 0 && row.distinctEcgs > 0)
          .map(([concept]) => concept);
        const resolution = handoffFocus ? resolveHandoffTarget(handoffFocus, available) : null;
        setHandoffResolution(resolution);
        if (handoffFocus && !resolution) {
          setHandoffUnavailable(`No automated-screened formative case family can currently support ${handoffFocus.replaceAll("_", " ")}. The handoff is locked; no substitute case or competency receipt will be created.`);
        }
      })
      .catch(() => {
        if (!cancelled && handoffFocus) {
          setHandoffResolution(null);
          setHandoffUnavailable("Clinical case coverage could not be verified. This handoff is locked until the live bank contract is available.");
        }
      })
      .finally(() => { if (!cancelled) setCoverageReady(true); });
    return () => { cancelled = true; };
  }, [handoffFocus]);

  useEffect(() => {
    let cancelled = false;
    setHydrating(true);
    clinicalApi.active()
      .then((lifecycle) => {
        if (cancelled || !lifecycle.session) return;
        setSession(lifecycle.session);
        setLane(lifecycle.session.lane);
        setMode(lifecycle.session.tier);
        setLength(lifecycle.session.length);
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
  }, [identityKey]);

  // clock
  const [remaining, setRemaining] = useState(0);
  const [running, setRunning] = useState(false);
  const [phaseReady, setPhaseReady] = useState(false);
  const clockEndRef = useRef<number>(0);
  const activationRef = useRef("");

  const item = current?.item ?? null;
  const isShift = mode === "shift";
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
      setError("The server returned an invalid Clinical phase deadline.");
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

  useEffect(() => {
    if (phase !== "decide") return;
    const frame = window.requestAnimationFrame(() => {
      contextRef.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
      contextRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [phase]);

  const submit = useCallback(
    async () => {
      if (!session || !current?.itemId || !current.item || phase === "feedback") return;
      stopClock();
      setBusy(true);
      setError(null);
      const payload: ClinicalAnswerPayload = {
        ...answer,
      };
      try {
        const { grade: g } = await clinicalApi.answer(session.sessionId, current.itemId, payload);
        setGrade(g);
        setCompetencyReceipt(null);
        const exactReceipts = g.competencyReceipts ?? [];
        if (handoffFocus && handoffSubskill && handoffResolution) {
          const receipt = exactReceipts.find((candidate) => (
            candidate.concept === handoffResolution.caseConcept && candidate.subskill === handoffSubskill
          ));
          if (!receipt) {
            setCompetencyReceipt(
              `No ${handoffSubskill.replaceAll("_", " ")} receipt: this item did not carry that exact server-graded Clinical competency cell.`,
            );
          } else {
            setCompetencyReceipt(
              `Server-graded formative ${receipt.subskill.replaceAll("_", " ")} ${receipt.correct ? "success" : "attempt"} recorded for ${receipt.concept.replaceAll("_", " ")} · ${Math.round(receipt.formativeScore * 100)}% formative evidence. Independent and retention credit remain locked pending named clinician sign-off.`,
            );
          }
        } else if (exactReceipts.length) {
          const receipt = exactReceipts[0];
          setCompetencyReceipt(
            `${exactReceipts.length} exact server-graded formative receipt${exactReceipts.length === 1 ? "" : "s"} saved; first: ${receipt.concept.replaceAll("_", " ")} · ${receipt.subskill.replaceAll("_", " ")}. Independent and retention credit remain locked pending named clinician sign-off.`,
          );
        }
        setPhase("feedback");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not grade the answer.");
      } finally {
        setBusy(false);
      }
    },
    [session, current, answer, phase, stopClock, handoffFocus, handoffSubskill, handoffResolution],
  );

  // Orientation and decision are deliberately partitioned. Expiring the ECG-only
  // first-look clock must never submit an answer before clinical choices and a
  // confidence control are available; revealing context starts a fresh decision clock.
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      const rem = Math.max(0, (clockEndRef.current - performance.now()) / 1000);
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
    if (!session || !current?.itemId || phase === "feedback") return;
    const activationKey = `${session.sessionId}:${current.itemId}:${phase}`;
    if (activationRef.current === activationKey) return;
    activationRef.current = activationKey;
    // This request is the durable readiness boundary: navigation/request time
    // never starts a Clinical assessment clock.
    void clinicalApi.activatePhase(session.sessionId, current.itemId, phase)
      .then((activated) => {
        setCurrent(activated);
        setPhaseReady(true);
        syncPhaseClock(activated, phase);
      })
      .catch((e) => {
        activationRef.current = "";
        setError(e instanceof Error ? e.message : "Could not activate the Clinical phase clock.");
      });
  }, [session, current?.itemId, phase, syncPhaseClock]);

  async function startShift() {
    if (handoffFocus && !coverageReady) {
      setError("Verifying the live Clinical case coverage for this handoff. Try again in a moment.");
      return;
    }
    if (handoffFocus && !handoffResolution) {
      setError(handoffUnavailable || "This handoff has no automated-screened formative case family.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { session: s, next } = await clinicalApi.start({
        lane,
        tier: mode,
        length,
        focus: handoffResolution?.caseConcept,
        subskill: handoffSubskill ?? undefined,
      });
      if (!next.item) {
        setError(next.reason || "No compatible automated-screened formative item is available in this lane.");
        setView("picker");
        return;
      }
      setSession(s);
      loadNext(next);
      setView("runner");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the shift.");
    } finally {
      setBusy(false);
    }
  }

  function loadNext(next: NextResult) {
    setGrade(null);
    setAnswer(next.firstLook ? {
      firstLookFinding: next.firstLook.firstLookFinding,
      firstLookConfidence: next.firstLook.firstLookConfidence,
    } : {});
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
      setPhaseReady(true);
      activationRef.current = `${session.sessionId}:${current.itemId}:decide`;
      syncPhaseClock(revealed, "decide");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reveal the clinical context.");
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
      setError(e instanceof Error ? e.message : "Could not advance the shift.");
    } finally {
      setBusy(false);
    }
  }

  // --- render ---------------------------------------------------------------
  if (view === "picker") {
    return (
      <div className="clinical-shell">
        <header className="page-header">
          <div>
            <span className="eyebrow"><Stethoscope size={15} aria-hidden="true" /> Mode 04 · Clinical decisions</span>
            <h1>Use the ECG to make<br />the next decision.</h1>
            <p className="muted">
              Situation-framed cases where the ECG changes triage, medication safety, disposition, or follow-up.
              The tracing is real when labeled; the board-style context is authored and disclosed.
            </p>
          </div>
          {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} /> Return to lesson</Link> : null}
        </header>
        {handoffFocus ? (
          <div className="selection-note" style={{ marginBottom: 14 }}>
            Guided handoff: apply <strong>{handoffFocus ? handoffFocus.replaceAll("_", " ") : "the scene objective"}</strong>
            {handoffSubskill ? <> through <strong>{handoffSubskill.replaceAll("_", " ")}</strong></> : null} in a clinical context.
            {handoffResolution ? <> The harness-checked formative target is <strong>{handoffResolution.caseConcept.replaceAll("_", " ")}</strong>{handoffResolution.exact ? "." : ` because ${handoffResolution.rationale}.`}</> : null} ECG recognition and management are scored as separate evidence axes.
          </div>
        ) : null}
        {handoffUnavailable ? <div className="warning" role="alert" style={{ marginBottom: 14 }}>{handoffUnavailable}</div> : null}
        {error ? <div className="warning">{error}</div> : null}
        <section className="panel pad clinical-picker">
          <div className="field">
            <label>Setting</label>
            <div className="segmented">
              {LANES.map((l) => (
                <button key={l} type="button" className={l === lane ? "active" : ""} aria-pressed={l === lane} onClick={() => setLane(l)}>
                  {LANE_LABEL[l]}
                </button>
              ))}
              <button type="button" disabled title="Requires a validated acute rhythm/telemetry corpus">
                Critical care · data needed
              </button>
            </div>
            <p className="muted clinical-data-boundary">Resuscitation and ACLS scenarios stay locked until a separately validated acute rhythm dataset is connected. Resting PTB-XL tracings are not used to fake code cases.</p>
          </div>
          <div className="field">
            <label>Mode</label>
            <div className="segmented">
              <button type="button" className={mode === "learn" ? "active" : ""} aria-pressed={mode === "learn"} onClick={() => setMode("learn")}>
                Learn (untimed)
              </button>
              <button type="button" className={mode === "shift" ? "active" : ""} aria-pressed={mode === "shift"} onClick={() => setMode("shift")}>
                Shift (timed)
              </button>
            </div>
          </div>
          <div className="field">
            <label>Length</label>
            <div className="segmented">
              {LENGTHS.map((n) => (
                <button key={n} type="button" className={n === length ? "active" : ""} aria-pressed={n === length} onClick={() => setLength(n)}>
                  {n} cases
                </button>
              ))}
            </div>
          </div>
          <button className="button primary" type="button" onClick={() => void startShift()} disabled={busy || hydrating || Boolean(handoffUnavailable) || Boolean(handoffFocus && !coverageReady)}>
            <Activity size={16} aria-hidden="true" /> {hydrating ? "Checking for saved shift…" : handoffFocus && !coverageReady ? "Verifying case coverage…" : busy ? "Starting..." : "Start shift"} <ArrowRight size={16} aria-hidden="true" />
          </button>
          <p className="clinical-authorship-note"><ShieldCheck size={14} aria-hidden="true" /> Board-style context · recording provenance shown on every case · educational use only</p>
        </section>
      </div>
    );
  }

  if (view === "report" && report) {
    return (
      <div className="clinical-shell">
        <header className="page-header">
          <div>
            <span className="eyebrow"><CheckCircle2 size={15} aria-hidden="true" /> Shift complete</span>
            <h1>{LANE_LABEL[report.lane]} · {report.tier === "learn" ? "Learn" : "Shift"}</h1>
          </div>
          {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} /> Return to lesson</Link> : null}
        </header>
        <section className="panel pad clinical-report">
          <div className="clinical-metric"><strong>{Math.round(report.accuracy * 100)}%</strong><span>accuracy</span></div>
          <div className="clinical-metric"><strong>{report.bestStreak}</strong><span>best streak</span></div>
          <div className="clinical-metric"><strong>{report.answered}/{report.length}</strong><span>answered</span></div>
          <div className="clinical-metric"><strong>{report.avgDecideMs != null ? `${(report.avgDecideMs / 1000).toFixed(1)}s` : "—"}</strong><span>avg decide</span></div>
          <div className="clinical-metric wide"><strong>{report.calibrationLabel}</strong><span>calibration</span></div>
        </section>
        <button className="button primary" type="button" onClick={() => setView("picker")}>New shift</button>
      </div>
    );
  }

  if (!item) {
    return <div className="clinical-shell"><div className="panel pad">{error ?? "Loading…"}</div></div>;
  }

  const labels = phaseLabels(item.situation);
  const phaseLabel = untimed ? null : phase === "orient" ? labels.orient : labels.decide;
  const total = phase === "orient" ? (current?.clock?.orientSec ?? 0) : (current?.clock?.decideSec ?? 0);
  const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0;
  const timedOut = phase === "feedback" && grade?.timedOut;
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

  return (
    <div className="clinical-shell">
      <header className="clinical-hud">
        <span className="pill"><Stethoscope size={14} aria-hidden="true" /> {LANE_LABEL[item.situation]}</span>
        <span className="pill subtle">{questionTypeLabel(item.question_type)}</span>
        <span className="muted">Case {current!.index + 1} / {current!.total}</span>
        <span className="clinical-provenance muted">{provenanceBadge(item.tracing_provenance)}</span>
        <span className="pill subtle">Formative only</span>
        {returnTo ? <Link className="button subtle small" href={returnTo}><ArrowLeft size={15} /> Return to lesson</Link> : null}
      </header>

      {phase === "feedback" ? (
        <div className="clinical-clock complete" data-clock-phase="feedback">
          <CheckCircle2 size={14} aria-hidden="true" /> <span>Decision submitted</span>
        </div>
      ) : !untimed ? (
        <div className={`clinical-clock${phase === "decide" ? " decide" : ""}`} data-clock-phase={phase}>
          <Timer size={14} aria-hidden="true" />
          <span>{phaseLabel}</span>
          <div className="clinical-clockbar"><i style={{ width: `${pct}%` }} /></div>
          <span>{Math.ceil(remaining)}s</span>
        </div>
      ) : (
        <div className="clinical-clock untimed"><Clock size={14} aria-hidden="true" /> <span>Learn — untimed</span></div>
      )}

      {phase === "orient" ? (
        <div className="selection-note clinical-context-mask">
          <strong>ECG-only first look.</strong> The authored symptom, bedside context, and decision prompt stay masked until you inspect the tracing. This prevents the vignette from giving away the ECG finding.
        </div>
      ) : (
        <div ref={contextRef} tabIndex={-1} className="panel pad clinical-stem" aria-label="Clinical context and decision prompt">
          <p>{item.stem}</p>
          {item.chips ? (
            <div className="clinical-chips">
              {item.chips.age != null ? <span className="chip">{item.chips.age}y</span> : null}
              {item.chips.bp ? <span className="chip">BP {item.chips.bp}</span> : null}
              {item.chips.symptom && item.chips.symptom !== "none" ? <span className="chip">{item.chips.symptom.replace(/_/g, " ")}</span> : null}
              {item.chips.mental_status ? <span className="chip">{item.chips.mental_status}</span> : null}
            </div>
          ) : null}
        </div>
      )}

      {/* Display */}
      {item.display_spec.mode === "stacked_twelve_lead" && item.prior_ecg_id ? (
        <div className="clinical-stacked">
          <div><div className="clinical-strip-label">Today</div><ECGViewer caseId={item.ecg_id} onReady={onReady} actions={feedbackActions} /></div>
          <div><div className="clinical-strip-label">Prior</div><ECGViewer caseId={item.prior_ecg_id} toolbar="none" /></div>
        </div>
      ) : (
        <>
          <ECGViewer
            caseId={item.ecg_id}
            onReady={onReady}
            actions={feedbackActions}
            task={clinicalViewerTask}
            onTaskEvidence={clinicalViewerTask ? captureClinicalPoint : undefined}
            onCoordinate={
              !clinicalViewerTask && (item.question_type === "click" || item.question_type === "spoterror")
                ? (p: ECGPoint) => setAnswer((a) => ({ ...a, click: { lead: p.lead, timeSec: p.timeSec, amplitudeMv: p.amplitudeMv } }))
                : undefined
            }
          />
          {item.display_spec.mode === "twelve_lead_pinned_strip" ? (
            <PinnedRhythmStrip caseId={item.ecg_id} lead={item.display_spec.pinned_strip_lead ?? "II"} />
          ) : null}
        </>
      )}

      {phase === "orient" ? (
        <div className="panel pad clinical-first-look">
          <strong>Commit an ECG-only first look before opening the case.</strong>
          <p className="muted">This response is attached to the item, but it is not treated as independent recognition mastery unless the case contract can actually grade it.</p>
          <div className="clinical-first-look-fields">
            <label htmlFor="clinical-first-look">Dominant finding</label>
            <select
              id="clinical-first-look"
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
          <button className="button primary" type="button" disabled={busy || (!untimed && !phaseReady) || !answer.firstLookFinding || !answer.firstLookConfidence} onClick={() => void commitFirstLook()}>
            {busy ? "Saving first look…" : "Commit first look & reveal clinical context"} <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      {/* Machine-read panel for spot-the-error */}
      {phase !== "orient" && item.question_type === "spoterror" && item.machine_read ? (
        <div className="panel pad clinical-machine">
          <div className="clinical-strip-label">Machine read — click the wrong line</div>
          {item.machine_read.map((ln) => (
            <button
              key={ln.id}
              type="button"
              className={`clinical-machine-line${answer.machineLineId === ln.id ? " selected" : ""}`}
              aria-pressed={answer.machineLineId === ln.id}
              disabled={phase === "feedback"}
              onClick={() => setAnswer((a) => ({ ...a, machineLineId: ln.id }))}
            >
              {ln.text}
            </button>
          ))}
        </div>
      ) : null}

      {/* Question / answer area */}
      {phase !== "orient" ? <div className="panel pad clinical-question">
        <strong>{item.prompt}</strong>
        {item.question_type === "stepwise" && item.steps?.length ? (
          <div className="clinical-stepwise" aria-label="Stepwise ECG interpretation">
            {item.steps.map((step, stepIndex) => (
              <fieldset key={`${item.item_id}-step-${stepIndex}`}>
                <legend>{stepIndex + 1}. {step.prompt}</legend>
                {step.options.map((option, optionIndex) => (
                  <button
                    key={`${stepIndex}-${optionIndex}`}
                    type="button"
                    className={answer.stepAnswers?.[stepIndex] === optionIndex ? "selected" : ""}
                    aria-pressed={answer.stepAnswers?.[stepIndex] === optionIndex}
                    disabled={phase === "feedback"}
                    onClick={() => setAnswer((currentAnswer) => {
                      const stepAnswers = [...(currentAnswer.stepAnswers ?? [])];
                      stepAnswers[stepIndex] = optionIndex;
                      return { ...currentAnswer, stepAnswers };
                    })}
                  >{option.text}</button>
                ))}
              </fieldset>
            ))}
          </div>
        ) : null}
        {item.options && item.options.length ? (
          <div className="clinical-options">
            {item.options.map((opt) => (
              <button
                key={opt.id}
                type="button"
                className={`clinical-option${answer.selectedOptionId === opt.id ? " selected" : ""}${
                  phase === "feedback" ? " locked" : ""
                }`}
                aria-pressed={answer.selectedOptionId === opt.id}
                disabled={phase === "feedback"}
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

        {isShift && phase !== "feedback" && (item.options?.length || item.question_type === "spoterror") ? (
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

        {phase !== "feedback" ? (
          <button className="button primary" type="button" disabled={busy || !canSubmit(item, answer, isShift)} onClick={() => void submit()}>
            Submit
          </button>
        ) : null}
      </div> : null}

      {/* Feedback */}
      {phase === "feedback" && grade ? (
        <div className={`panel pad clinical-feedback ${grade.score >= 0.6 ? "ok" : "miss"}`}>
          <h2>
            <HeartPulse size={18} aria-hidden="true" />{" "}
            {timedOut ? "Time" : grade.score >= 0.6 ? "Good decision" : "Reconsider"} · {Math.round(grade.score * 100)}%
            {grade.answerClass ? <span className="pill subtle">{grade.answerClass.replace(/_/g, " ")}</span> : null}
          </h2>
          <p>{grade.feedback}</p>
          {grade.clinicalApplicationEvidence === "formative_only" ? (
            <p className="selection-note">Clinical application is formative practice only; it does not raise independent application mastery.</p>
          ) : null}
          {grade.ecgRecognitionSuppressed ? (
            <p className="selection-note">
              ECG-recognition mastery was not updated because the stem disclosed: {(grade.stemDisclosedObjectives ?? []).map((item) => item.replaceAll("_", " ")).join(", ")}. The clinical decision score remains separate.
            </p>
          ) : null}
          {competencyReceipt ? <p className="selection-note" role="status">{competencyReceipt}</p> : null}
          {grade.safetyFlags?.length ? (
            <p className="warning">Safety: {grade.safetyFlags.join(", ").replace(/_/g, " ")}</p>
          ) : null}
          {Object.keys(grade.axisScores ?? {}).length ? (
            <div className="clinical-axes">
              {Object.entries(grade.axisScores).map(([k, v]) => (
                <div key={k} className="clinical-axis">
                  <span>{k.replace(/_/g, " ")}</span>
                  <div className="mastery-bar"><i style={{ width: `${Math.round((v as number) * 100)}%` }} /></div>
                </div>
              ))}
            </div>
          ) : null}
          {grade.teachingPoints?.length ? <p className="muted">{grade.teachingPoints.join(" ")}</p> : null}
          <TutorChat
            mode="practice"
            roleLabel="Attending challenge · post-commit"
            caseId={item.ecg_id}
            openingPrompt="Ask why the ECG changed the decision, request a grounded highlight, or reason through the closest safe alternative."
            viewerState={{
              activity: "clinical_case_debrief",
              situation: item.situation,
              questionType: item.question_type,
              prompt: item.prompt,
              score: grade.score,
              correctObjectives: grade.correctObjectives,
              missedObjectives: grade.missedObjectives,
              safetyFlags: grade.safetyFlags,
              committed: true,
            }}
            onViewerActions={setAiViewerActions}
            resetKey={item.item_id}
            collapsedByDefault
          />
          <button className="button primary" type="button" onClick={() => void goNext()} disabled={busy}>
            {current!.index + 1 >= current!.total ? "Finish shift" : "Next case"} <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      ) : null}
      {error ? <div className="warning">{error}</div> : null}
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
  const needConfidence = isShift && (Boolean(item.options?.length) || item.question_type === "spoterror");
  if (needConfidence && !answer.confidence) return false;
  if (item.question_type === "click") return Boolean(answer.click);
  if (item.question_type === "spoterror") return Boolean(answer.click && answer.machineLineId);
  if (item.question_type === "stepwise") {
    const complete = Boolean(item.steps?.length) && item.steps!.every((step, index) => {
      const selected = answer.stepAnswers?.[index];
      return selected != null && selected >= 0 && selected < step.options.length;
    });
    return complete && Boolean(answer.selectedOptionId);
  }
  if (item.options?.length) return Boolean(answer.selectedOptionId);
  return true;
}

function questionTypeLabel(questionType: NonNullable<NextResult["item"]>["question_type"]): string {
  const labels = {
    triage: "Prioritize care",
    stepwise: "Stepwise decision",
    click: "Prove it on the ECG",
    spoterror: "Audit the machine read",
    oldnew: "Compare prior ECG",
    mcq: "Clinical decision",
  } as const;
  return labels[questionType];
}
