"use client";

import { BookOpen, CheckCircle2, MousePointerClick, Send, Target, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { api, type TutorialLesson } from "@/lib/api";
import { conceptLabel, type ECGPoint } from "@/lib/coordinates";
import type { CasePacket, CaseSummary, LearnerProfile, ViewerAction } from "@/lib/types";

type TutorialListItem = {
  id: string;
  title: string;
  objectives: string[];
  caseConcept: string | null;
  steps: string[];
};

function masteryClass(value: number) {
  if (value < 0.45) return "low";
  if (value < 0.7) return "medium";
  return "";
}

export default function TutorialsPage() {
  const [tutorials, setTutorials] = useState<TutorialListItem[]>([]);
  const [selectedId, setSelectedId] = useState("orientation");
  const [lesson, setLesson] = useState<TutorialLesson | null>(null);
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [openingPrompt, setOpeningPrompt] = useState("");
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewerActions, setViewerActions] = useState<ViewerAction[]>([]);
  const [masteryRows, setMasteryRows] = useState<LearnerProfile["mastery"]>([]);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("lesson");
    if (requested) setSelectedId(requested);
  }, []);

  useEffect(() => {
    api
      .tutorials()
      .then((data) => setTutorials(data.tutorials))
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setFeedback(null);
    setAnswer("");
    setSelectedPoint(null);
    setViewerActions([]);
    api
      .tutorial(selectedId)
      .then(async (data) => {
        if (cancelled) return;
        setLesson(data.lesson);
        setOpeningPrompt(data.openingPrompt);
        setCaseSummary(data.recommendedCase);
        setPacket(await api.packet(data.recommendedCase.caseId));
      })
      .catch((err: Error) => setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const handleViewerActions = useCallback((actions: ViewerAction[]) => {
    setViewerActions(actions);
  }, []);

  const viewerState = useMemo(() => ({ selectedPoint }), [selectedPoint]);
  // The explicit click-task schema drives the identify-feature / click-grade mode.
  // When null, there is no click target for this lesson and we fall back to the structured submit only.
  const clickTask = lesson?.clickTask ?? null;
  const lessonReturnPrompt = useMemo(() => {
    const step = lesson?.steps[0];
    return step ? `Let's get back to the lesson: ${step}` : "Let's return to this lesson's objective.";
  }, [lesson]);

  const refreshMastery = useCallback(async () => {
    try {
      const profile = await api.mastery("demo");
      const focus = lesson?.objectives ?? [];
      const rows = profile.mastery
        .filter((row) => focus.includes(row.objective))
        .sort((a, b) => a.mastery - b.mastery);
      setMasteryRows(rows.length ? rows : profile.mastery.slice(0, 4));
    } catch {
      // Mastery readback is best-effort; ignore failures.
    }
  }, [lesson]);

  async function submitAnswer() {
    const expected = lesson?.objectives.map(conceptLabel).join(", ") ?? "the current objective";
    if (answer.trim().length < 8) {
      setFeedback(`Try naming an ECG feature tied to ${expected}.`);
      return;
    }
    if (!caseSummary || !lesson) {
      setFeedback("Load a grounded tutorial case before checking an answer.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await api.submitAttempt({
        learnerId: "demo",
        caseId: caseSummary.caseId,
        mode: "tutorial",
        structuredAnswer: {
          framework: "clerkship",
          rate: "",
          rhythm: "",
          axis: "",
          intervals: "",
          conduction: "",
          st_t: "",
          hypertrophy: "",
          synthesis: answer.trim(),
          selectedConcepts: [],
        },
        freeTextAnswer: answer.trim(),
        confidence: 3,
        hintsUsed: 0,
      });
      const score = typeof response.grade.score === "number" ? `${Math.round(response.grade.score * 100)}%` : "graded";
      const gradeFeedback = typeof response.grade.feedback === "string" ? response.grade.feedback : `Compare your answer with ${expected}.`;
      setFeedback(`${score}: ${gradeFeedback}`);
      await refreshMastery();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit tutorial answer.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Guided curriculum</p>
          <h1>{lesson?.title ?? "ECG Orientation"}</h1>
          <p className="muted">Inspect the calibrated waveform, work through the lesson with the conversational tutor, then submit a graded read and watch mastery move.</p>
        </div>
      </header>

      {error ? <div className="warning">{error}</div> : null}

      <div className="grid two viewer-hero">
        <section className="grid">
          {caseSummary ? (
            <ECGViewer
              caseId={caseSummary.caseId}
              actions={viewerActions}
              groundedRois={packet?.ptbxl_plus.fiducials.rois ?? []}
              onCoordinate={setSelectedPoint}
              gradeConcept={clickTask ? clickTask.roiConcept : undefined}
              gradePrompt={clickTask ? clickTask.prompt : undefined}
              medianBeats={packet?.ptbxl_plus.median_beats ?? null}
            />
          ) : (
            <div className="panel pad">Loading tutorial case...</div>
          )}

          <section className="panel pad">
            <h2><BookOpen size={18} aria-hidden="true" /> Lesson Steps</h2>
            {openingPrompt ? <p className="selection-note">{openingPrompt}</p> : null}
            <div className="list">
              {lesson?.steps.map((step, index) => (
                <div className="list-item" key={step}>
                  <strong>{index + 1}. {step}</strong>
                </div>
              ))}
            </div>
            <div className="evidence-card" style={{ marginTop: 14 }}>
              <h3><MousePointerClick size={15} aria-hidden="true" /> Graded interaction</h3>
              {clickTask ? (
                <p className="muted" style={{ marginTop: 4 }}>
                  {clickTask.prompt} Use the target button on the viewer to identify {conceptLabel(clickTask.roiConcept)}
                  {clickTask.leads.length ? ` (look in ${clickTask.leads.join(", ")})` : ""}, or write a short read below and submit for a graded score.
                </p>
              ) : (
                <p className="muted" style={{ marginTop: 4 }}>
                  Write a short read below and submit for a graded score. This lesson has no single click target.
                </p>
              )}
            </div>
            <div className="form-grid" style={{ marginTop: 14 }}>
              <div className="field full">
                <label htmlFor="tutorial-answer">Your read</label>
                <textarea id="tutorial-answer" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Name the ECG feature, the lead(s), and why it supports your interpretation." />
              </div>
            </div>
            <div className="actions" style={{ marginTop: 12 }}>
              <button className="button primary" type="button" onClick={submitAnswer} disabled={!caseSummary || isSubmitting}>
                <Send size={17} aria-hidden="true" />
                {isSubmitting ? "Checking..." : "Submit graded read"}
              </button>
            </div>
            {feedback ? <p className="status-line" style={{ marginTop: 12 }}>{feedback}</p> : null}
            {masteryRows.length ? (
              <div className="profile-highlight" style={{ marginTop: 14, borderBottom: "none", paddingBottom: 0 }}>
                <h3><TrendingUp size={16} aria-hidden="true" /> Updated mastery</h3>
                <div className="list">
                  {masteryRows.slice(0, 5).map((row) => (
                    <div className="list-item objective-row" key={row.objective}>
                      <div className="objective-meta">
                        <strong>{conceptLabel(row.objective)}</strong>
                        <span className="muted">{Math.round(row.mastery * 100)}%</span>
                      </div>
                      <div className={`mastery-bar ${masteryClass(row.mastery)}`} aria-hidden="true"><span style={{ width: `${Math.round(row.mastery * 100)}%` }} /></div>
                      <p className="muted" style={{ margin: "8px 0 0" }}>{row.attempts} attempts, {row.correct} correct</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </section>

        <aside className="lesson-rail">
          {caseSummary ? (
            <TutorChat
              mode="tutorial"
              caseId={caseSummary.caseId}
              lessonId={lesson?.id}
              openingPrompt={openingPrompt}
              lessonReturnPrompt={lessonReturnPrompt}
              viewerState={viewerState}
              onViewerActions={handleViewerActions}
              resetKey={`${selectedId}-${caseSummary.caseId}`}
            />
          ) : null}

          <section className="panel pad">
            <h2>Curriculum</h2>
            <div className="list lesson-list">
              {tutorials.map((item) => (
                <button
                  className={`list-item${selectedId === item.id ? " active" : ""}`}
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                >
                  <strong>{item.title}</strong>
                  <div className="pill-row" style={{ marginTop: 8 }}>
                    {item.objectives.slice(0, 3).map((objective) => (
                      <span className="pill" key={objective}>{conceptLabel(objective)}</span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="panel pad">
            <h2><CheckCircle2 size={18} aria-hidden="true" /> Grounding</h2>
            <p className="muted">{caseSummary?.displayId ?? "No case selected"}</p>
            <div className="pill-row">
              <span className="pill">Tier {packet?.teaching_tier ?? "..."}</span>
              <span className="pill">{packet?.signal_quality.status ?? "quality"}</span>
              {lesson?.objectives.slice(0, 4).map((objective) => (
                <span className="pill" key={objective}>{conceptLabel(objective)}</span>
              ))}
            </div>
            <div className="evidence-grid" style={{ marginTop: 12 }}>
              <div className="evidence-card">
                <h3><Target size={16} aria-hidden="true" /> Lesson objectives</h3>
                <p className="muted">{lesson?.objectives.map(conceptLabel).join(", ") || "Loading objectives."}</p>
              </div>
              <div className="evidence-card">
                <h3>Selected point</h3>
                <p className="muted">{selectedPoint ? `${selectedPoint.lead} · ${selectedPoint.timeSec.toFixed(3)} sec · ${selectedPoint.amplitudeMv.toFixed(3)} mV` : "No ECG point selected."}</p>
              </div>
            </div>
            {packet?.exclusion_reasons.length ? <p className="uncertainty" style={{ marginTop: 12 }}>{packet.exclusion_reasons.slice(0, 2).join(" ")}</p> : null}
          </section>
        </aside>
      </div>
    </div>
  );
}
