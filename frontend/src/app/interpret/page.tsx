"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardList, Send, Target } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { api } from "@/lib/api";
import { conceptLabel, type ECGPoint } from "@/lib/coordinates";
import type { CasePacket, CaseSummary, ViewerAction } from "@/lib/types";

// Backend structuredAnswer keys (fixed by the API contract).
type AnswerKey = "rate" | "rhythm" | "axis" | "intervals" | "conduction" | "st_t" | "hypertrophy";

type FrameworkField = { key: AnswerKey; label: string };
type FrameworkSection = { id: string; heading: string; fields: FrameworkField[] };

// Standard clerkship order: Rate, Rhythm, Axis, Intervals, QRS, ST-T, Chambers.
const CLERKSHIP_SECTIONS: FrameworkSection[] = [
  {
    id: "clerkship",
    heading: "Clerkship read",
    fields: [
      { key: "rate", label: "Rate" },
      { key: "rhythm", label: "Rhythm" },
      { key: "axis", label: "Axis" },
      { key: "intervals", label: "Intervals" },
      { key: "conduction", label: "Conduction / QRS" },
      { key: "st_t", label: "ST-T / ischemia" },
      { key: "hypertrophy", label: "Hypertrophy / chambers" },
    ],
  },
];

// HEARTS sequence: H rate&rhythm, E axis, A atria&intervals, R R-wave/QRS&conduction, T T-waves&ST, S synthesis.
const HEARTS_SECTIONS: FrameworkSection[] = [
  {
    id: "H",
    heading: "H — Heart rate & rhythm",
    fields: [
      { key: "rate", label: "Rate" },
      { key: "rhythm", label: "Rhythm" },
    ],
  },
  {
    id: "E",
    heading: "E — Electrical axis",
    fields: [{ key: "axis", label: "Axis" }],
  },
  {
    id: "A",
    heading: "A — Atria & intervals",
    fields: [
      { key: "intervals", label: "Intervals (PR / QT)" },
      { key: "hypertrophy", label: "Atrial / chamber enlargement" },
    ],
  },
  {
    id: "R",
    heading: "R — R-wave progression & QRS / conduction",
    fields: [{ key: "conduction", label: "QRS / conduction & R-wave progression" }],
  },
  {
    id: "T",
    heading: "T — T waves & ST segments",
    fields: [{ key: "st_t", label: "ST-T / repolarization" }],
  },
];

type SelectionState = {
  reason: string;
  targetObjectives: string[];
};

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function sourceLabel(source?: string) {
  if (source === "fixture") return "Demo fixture";
  if (source === "prepared_bundle") return "Prepared PTB-XL bundle";
  if (source === "ptbxl") return "Local PTB-XL/PTB-XL+";
  return source ? source.replaceAll("_", " ") : "Loading";
}

function masteryClass(value: number) {
  if (value < 0.45) return "low";
  if (value < 0.7) return "medium";
  return "";
}

export default function PracticePage() {
  return (
    <Suspense fallback={<div className="page"><div className="panel pad">Loading practice workspace...</div></div>}>
      <PracticeWorkspace />
    </Suspense>
  );
}

function PracticeWorkspace() {
  const search = useSearchParams();
  const concept = search.get("concept") ?? undefined;
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [selection, setSelection] = useState<SelectionState | null>(null);
  const [emptyReason, setEmptyReason] = useState<string | null>(null);
  const [framework, setFramework] = useState<"clerkship" | "hearts">("clerkship");
  const [answer, setAnswer] = useState<Record<string, string>>({});
  const [freeText, setFreeText] = useState("");
  const [confidence, setConfidence] = useState(3);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [viewerActions, setViewerActions] = useState<ViewerAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadNext(concept);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [concept]);

  const groundedRois = packet?.ptbxl_plus.fiducials.rois ?? [];
  const topConcepts = useMemo(() => packet?.supported_objectives?.slice(0, 6) ?? [], [packet]);
  const confidenceRows = useMemo(
    () =>
      packet?.concept_confidence
        ? Object.entries(packet.concept_confidence)
            .sort(([, left], [, right]) => right.score - left.score)
            .slice(0, 4)
        : [],
    [packet],
  );
  const sections = framework === "hearts" ? HEARTS_SECTIONS : CLERKSHIP_SECTIONS;
  const sequenceTags = framework === "hearts"
    ? ["H Rate/Rhythm", "E Axis", "A Atria/Intervals", "R QRS/Conduction", "T T-waves/ST", "S Synthesis"]
    : ["Rate", "Rhythm", "Axis", "Intervals", "QRS", "ST-T", "Chambers", "Synthesis"];

  const gradeScore = typeof result?.score === "number" ? Math.round(result.score * 100) : null;
  const feedback = typeof result?.feedback === "string" ? result.feedback : "";
  const correctObjectives = asStringArray(result?.correctObjectives);
  const missedObjectives = asStringArray(result?.missedObjectives);
  const overcalledObjectives = asStringArray(result?.overcalledObjectives);
  const misconceptions = asStringArray(result?.misconceptions);
  const teachingPoints = asStringArray(result?.teachingPoints);
  const revealedDiagnosis = typeof result?.revealedDiagnosis === "string" ? result.revealedDiagnosis : "";

  async function loadNext(targetConcept?: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    setViewerActions([]);
    setEmptyReason(null);
    try {
      const next = await api.nextCase("demo", targetConcept);
      if (!next.case) {
        setCaseSummary(null);
        setPacket(null);
        setSelection(null);
        setEmptyReason(next.reason || "No reliable case is available for this selection yet.");
        return;
      }
      // Pre-submission: fetch the BLINDED packet so the answer key (diagnosis,
      // concept confidence, report, teaching points) never reaches the client.
      const packetData = await api.packet(next.case.caseId, { blinded: true });
      setCaseSummary(next.case);
      setPacket(packetData);
      setSelection({ reason: next.reason, targetObjectives: next.targetObjectives });
      setAnswer({});
      setFreeText("");
      setConfidence(3);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const handleViewerActions = useCallback((actions: ViewerAction[]) => {
    setViewerActions(actions);
  }, []);

  const viewerState = useMemo(() => ({ selectedPoint }), [selectedPoint]);

  async function submit() {
    if (!caseSummary) return;
    setLoading(true);
    setError(null);
    try {
      const body = {
        learnerId: "demo",
        caseId: caseSummary.caseId,
        mode: concept ? "concept_practice" : "rapid_practice",
        // Pin the practiced concept so concept-specific review actually moves its mastery.
        focusObjective: concept,
        structuredAnswer: {
          framework,
          rate: answer.rate ?? "",
          rhythm: answer.rhythm ?? "",
          axis: answer.axis ?? "",
          intervals: answer.intervals ?? "",
          conduction: answer.conduction ?? "",
          st_t: answer.st_t ?? "",
          hypertrophy: answer.hypertrophy ?? "",
          synthesis: answer.synthesis ?? "",
          selectedConcepts: [],
        },
        freeTextAnswer: freeText,
        confidence,
        hintsUsed: 0,
      };
      const response = await api.submitAttempt(body);
      // Reveal the FULL packet BEFORE flipping `result`, so the reveal UI never
      // renders against the blinded packet (which omits diagnosis-bearing fields
      // such as exclusion_reasons / ptbxl labels) and crashes on undefined.length
      // (V1 audit: practice crashed on submit).
      try {
        const fullPacket = await api.packet(caseSummary.caseId);
        setPacket(fullPacket);
      } catch {
        // If the reveal fetch fails, keep the blinded packet; the guarded reveal fields still render.
      }
      setResult(response.grade);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">{concept ? "Concept practice" : "ECG interpretation"}</p>
          <h1>{caseSummary?.displayId ?? (emptyReason ? "No case available" : "Loading ECG case")}</h1>
          <p className="muted">{packet?.clinical_stem ?? emptyReason ?? "Fetching the next confidence-gated teaching case."}</p>
        </div>
        <div className="actions">
          <button className="button" type="button" onClick={() => loadNext(concept)} disabled={loading}>
            Next case
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        </div>
      </header>

      {error ? <div className="warning">{error}</div> : null}

      {selection ? (
        <section className="selection-note" style={{ marginBottom: 16 }}>
          <div className="case-label"><Target size={16} aria-hidden="true" /> Adaptive selection</div>
          <p className="muted" style={{ margin: "6px 0 10px" }}>{selection.reason}</p>
          {/* Target objectives name the case's findings, so they stay hidden until after submission. */}
          {result ? (
            <div className="pill-row">
              {selection.targetObjectives.slice(0, 6).map((objective) => (
                <span className="pill" key={objective}>{conceptLabel(objective)}</span>
              ))}
            </div>
          ) : (
            <p className="muted" style={{ margin: 0, fontStyle: "italic" }}>Focus areas are revealed after you submit your read.</p>
          )}
        </section>
      ) : null}

      <div className="grid two viewer-hero">
        <div className="grid">
          {caseSummary ? (
            <ECGViewer
              caseId={caseSummary.caseId}
              actions={viewerActions}
              groundedRois={result ? groundedRois : []}
              onCoordinate={setSelectedPoint}
              medianBeats={packet?.ptbxl_plus.median_beats ?? null}
            />
          ) : (
            <div className="panel pad">{emptyReason ?? "Loading viewer..."}</div>
          )}
          {packet ? (
            <section className="panel pad">
              <h2><ClipboardList size={18} aria-hidden="true" /> {result ? "Grounded Case Packet" : "Case Brief"}</h2>
              <div className="pill-row">
                <span className="pill">Tier {packet.teaching_tier}</span>
                <span className="pill">{sourceLabel(packet.source)}</span>
                <span className="pill">{packet.signal_quality.status}</span>
                {result ? topConcepts.map((objective) => (
                  <span className="pill" key={objective}>{conceptLabel(objective)}</span>
                )) : null}
              </div>
              {packet.source === "fixture" ? (
                <p className="warning" style={{ marginTop: 12 }}>Demo waveform: non-clinical fixture data for local verification and walkthroughs.</p>
              ) : null}
              {!result ? (
                <p className="selection-note" style={{ marginTop: 12 }}>
                  <Target size={15} aria-hidden="true" /> Interpret first, then submit. The grounded labels, report, and concept reliability stay hidden until your interpretation is graded.
                </p>
              ) : null}
              {result ? (
                <>
                  {packet.exclusion_reasons?.length ? (
                    <p className="uncertainty" style={{ marginTop: 12 }}>
                      <AlertTriangle size={15} aria-hidden="true" /> Uncertain or excluded findings: {packet.exclusion_reasons.slice(0, 2).join(" ")}
                    </p>
                  ) : null}
                  <div className="evidence-grid" style={{ marginTop: 12 }}>
                    <div className="evidence-card">
                      <h3>PTB-XL labels</h3>
                      <p className="muted">{packet.ptbxl?.diagnostic_superclass?.join(", ") || "No diagnostic superclass supplied."}</p>
                      <p className="muted">{packet.ptbxl?.report || caseSummary?.report}</p>
                    </div>
                    <div className="evidence-card">
                      <h3>PTB-XL+ evidence</h3>
                      <div className="compact-list">
                        {(packet.ptbxl_plus.statements ?? []).slice(0, 3).map((statement) => (
                          <p className="muted" key={statement}>{statement}</p>
                        ))}
                        {!packet.ptbxl_plus.statements?.length ? <p className="muted">No statement-level evidence available.</p> : null}
                        <p className="muted">{groundedRois.length} grounded ROI{groundedRois.length === 1 ? "" : "s"} available.</p>
                      </div>
                    </div>
                    <div className="evidence-card">
                      <h3>Concept reliability</h3>
                      <div className="compact-list">
                        {confidenceRows.map(([objective, row]) => (
                          <div key={objective}>
                            <div className="objective-meta">
                              <strong>{conceptLabel(objective)}</strong>
                              <span className="muted">Tier {row.tier} · {Math.round(row.score * 100)}%</span>
                            </div>
                            <div className={`mastery-bar ${masteryClass(row.score)}`} aria-hidden="true"><span style={{ width: `${Math.round(row.score * 100)}%` }} /></div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="evidence-card">
                      <h3>Inclusion reasons</h3>
                      <div className="compact-list">
                        <ul>
                          {(packet.inclusion_reasons ?? []).slice(0, 4).map((reason) => (
                            <li className="muted" key={reason}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                </>
              ) : null}
            </section>
          ) : null}
        </div>

        <aside className="lesson-rail">
          {caseSummary ? (
            <TutorChat
              mode="practice"
              caseId={caseSummary.caseId}
              viewerState={viewerState}
              onViewerActions={handleViewerActions}
              openingPrompt="Describe a finding and I will give a grounded visual hint, or ask me to point one out."
              resetKey={caseSummary.caseId}
            />
          ) : null}

          <section className="panel pad">
            <h2>Structured Interpretation</h2>
            <div className="segmented" aria-label="Interpretation framework">
              <button type="button" className={framework === "clerkship" ? "active" : ""} onClick={() => setFramework("clerkship")}>Clerkship</button>
              <button type="button" className={framework === "hearts" ? "active" : ""} onClick={() => setFramework("hearts")}>HEARTS</button>
            </div>
            <div className="interpretation-steps" aria-label="ECG interpretation workflow">
              {sequenceTags.map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
            </div>
            <div className="form-grid practice-form" style={{ marginTop: 14 }}>
              {sections.map((section) => (
                <div className="field full framework-section" key={section.id}>
                  {framework === "hearts" ? <p className="framework-heading">{section.heading}</p> : null}
                  <div className="framework-fields">
                    {section.fields.map((field) => (
                      <div className="field" key={field.key}>
                        <label htmlFor={field.key}>{field.label}</label>
                        <input
                          id={field.key}
                          value={answer[field.key] ?? ""}
                          onChange={(event) => setAnswer((current) => ({ ...current, [field.key]: event.target.value }))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <div className="field full">
                <label htmlFor="synthesis">{framework === "hearts" ? "S — Synthesis" : "Final synthesis"}</label>
                <textarea id="synthesis" value={answer.synthesis ?? ""} onChange={(event) => setAnswer((current) => ({ ...current, synthesis: event.target.value }))} />
              </div>
              <div className="field full">
                <label htmlFor="freeText">Free text</label>
                <textarea id="freeText" value={freeText} onChange={(event) => setFreeText(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="confidence">Confidence</label>
                <select id="confidence" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <option value={value} key={value}>{value}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Selected point</label>
                <div className="status-line">{selectedPoint ? `${selectedPoint.lead} · ${selectedPoint.timeSec.toFixed(3)} sec · ${selectedPoint.amplitudeMv.toFixed(3)} mV` : "No ECG point selected"}</div>
              </div>
            </div>
            <button className="button primary" type="button" onClick={submit} disabled={!caseSummary || loading} style={{ marginTop: 14 }}>
              <Send size={17} aria-hidden="true" />
              Submit interpretation
            </button>
          </section>

          {result ? (
            <section className="panel pad">
              <h2><CheckCircle2 size={18} aria-hidden="true" /> Feedback</h2>
              <div className="feedback-score">
                <strong>{gradeScore !== null ? `${gradeScore}%` : "Graded"}</strong>
                <span className="muted">case-specific interpretation score</span>
              </div>
              {feedback ? <p>{feedback}</p> : null}
              <div className="feedback-grid">
                <div className="evidence-card">
                  <h3>Correctly identified</h3>
                  <div className="pill-row">
                    {correctObjectives.length ? correctObjectives.map((item) => <span className="pill" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No grounded objectives matched yet.</span>}
                  </div>
                </div>
                <div className="evidence-card">
                  <h3>Review next</h3>
                  <div className="pill-row">
                    {missedObjectives.length ? missedObjectives.map((item) => <span className="pill disabled" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No missed grounded objectives.</span>}
                  </div>
                </div>
                <div className="evidence-card">
                  <h3>Overcalled</h3>
                  <div className="pill-row">
                    {overcalledObjectives.length ? overcalledObjectives.map((item) => <span className="pill disabled" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No unsupported calls detected.</span>}
                  </div>
                </div>
                <div className="evidence-card">
                  <h3>Misconceptions</h3>
                  <div className="pill-row">
                    {misconceptions.length ? misconceptions.map((item) => <span className="pill disabled" key={item}>{item.replaceAll("_", " ")}</span>) : <span className="muted">No misconception tag added.</span>}
                  </div>
                </div>
              </div>
              {teachingPoints.length ? (
                <>
                  <h3 style={{ marginTop: 14 }}>Teaching points</h3>
                  <div className="list">
                    {teachingPoints.map((point) => (
                      <div className="list-item" key={point}>{point}</div>
                    ))}
                  </div>
                </>
              ) : null}
              {revealedDiagnosis ? <p className="uncertainty" style={{ marginTop: 12 }}>Grounded reference: {revealedDiagnosis}</p> : null}
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
