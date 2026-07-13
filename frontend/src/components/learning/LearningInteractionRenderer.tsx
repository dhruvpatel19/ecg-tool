"use client";

import { ArrowDown, ArrowUp, CheckCircle2, CircleAlert, RotateCcw, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { feedbackFor, gradeInteraction } from "@/lib/learning/gradeInteraction";
import type { InteractionEvidence, LearningInteraction } from "@/lib/learning/interactionTypes";
import type { ViewerTaskEvidence } from "@/lib/types";

const ALL_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"];

type LearningInteractionRendererProps = {
  interaction: LearningInteraction;
  packetMeasurements?: Record<string, unknown>;
  viewerEvidence?: ViewerTaskEvidence | null;
  onEvidence: (evidence: InteractionEvidence) => void;
  savedEvidence?: InteractionEvidence;
};

function scrambledSequence(interaction: Extract<LearningInteraction, { kind: "sequence" }>) {
  const values = interaction.cards.map((card) => card.id);
  let seed = 2166136261;
  for (const character of interaction.id) {
    seed ^= character.charCodeAt(0);
    seed = Math.imul(seed, 16777619) >>> 0;
  }
  for (let index = values.length - 1; index > 0; index -= 1) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const swapIndex = seed % (index + 1);
    [values[index], values[swapIndex]] = [values[swapIndex], values[index]];
  }
  if (values.length > 1 && values.every((id, index) => id === interaction.correctOrder[index])) {
    values.push(values.shift() as string);
  }
  return values;
}

export function LearningInteractionRenderer({ interaction, packetMeasurements, viewerEvidence, onEvidence, savedEvidence }: LearningInteractionRendererProps) {
  const [attempts, setAttempts] = useState(savedEvidence?.attempts ?? 0);
  const [response, setResponse] = useState<unknown>(() => savedEvidence?.response ?? initialResponse(interaction));
  const [evidence, setEvidence] = useState<InteractionEvidence | null>(savedEvidence ?? null);

  useEffect(() => {
    setAttempts(savedEvidence?.attempts ?? 0);
    setResponse(savedEvidence?.response ?? initialResponse(interaction));
    setEvidence(savedEvidence ?? null);
  }, [interaction.id]);

  useEffect(() => {
    if (!viewerEvidence) return;
    if (interaction.kind === "point" && viewerEvidence.mode === "point") setResponse(viewerEvidence);
    if (interaction.kind === "region" && viewerEvidence.mode === "region") setResponse({ ...viewerEvidence, correct: viewerEvidence.correct });
    if (interaction.kind === "caliper" && viewerEvidence.mode === "caliper") setResponse({ ...viewerEvidence, valueMs: viewerEvidence.valueMs });
    if (interaction.kind === "march" && viewerEvidence.mode === "march") setResponse(viewerEvidence.points);
  }, [interaction.kind, viewerEvidence]);

  const feedback = evidence ? feedbackFor(interaction, evidence) : null;
  const notAssessable = evidence?.feedbackBranch === "not_assessable";
  const showScaffold = attempts >= interaction.maxAttemptsBeforeScaffold && !evidence?.correct;

  function submit() {
    const nextAttempts = attempts + 1;
    const result = gradeInteraction(interaction, response, nextAttempts, { packetMeasurements });
    setAttempts(nextAttempts);
    setEvidence(result);
    onEvidence(result);
  }

  function reset() {
    setResponse(initialResponse(interaction));
    setEvidence(null);
  }

  return (
    <section className="learning-interaction" aria-labelledby={`${interaction.id}-prompt`}>
      <header className="learning-interaction-head">
        <div>
          <p className="eyebrow"><Target size={14} /> Required ECG action · {interaction.kind.replaceAll("_", " ")}</p>
          <h3 id={`${interaction.id}-prompt`}>{interaction.prompt}</h3>
          <p>{interaction.instructions}</p>
        </div>
        <span>{attempts ? `${attempts} attempt${attempts === 1 ? "" : "s"}` : "Not submitted"}</span>
      </header>

      <div className="learning-interaction-body">
        <InteractionInput interaction={interaction} response={response} setResponse={setResponse} viewerEvidence={viewerEvidence} />
        {showScaffold ? (
          <div className="learning-scaffold" role="note">
            <strong>Smaller step</strong>
            <span>{feedback?.evidenceCue ?? interaction.accessibility.instructions}</span>
          </div>
        ) : null}
        {feedback ? (
          <div className={`learning-branch ${notAssessable ? "partial" : evidence?.correct ? "correct" : evidence?.partial ? "partial" : "incorrect"}`} role="status" aria-live="polite">
            {evidence?.correct && !notAssessable ? <CheckCircle2 size={19} /> : <CircleAlert size={19} />}
            <span><strong>{feedback.heading}</strong>{feedback.body}{feedback.nextPrompt ? <em>{feedback.nextPrompt}</em> : null}</span>
          </div>
        ) : null}
      </div>

      <footer className="learning-interaction-actions">
        <button className="button subtle" type="button" onClick={reset}><RotateCcw size={15} /> Reset response</button>
        <span className="muted">{interaction.subskills.map((skill) => skill.replaceAll("_", " ")).join(" · ")}</span>
        <button className="button primary" type="button" onClick={submit} disabled={!responseReady(interaction, response, viewerEvidence)}>Check my evidence</button>
      </footer>
    </section>
  );
}

function initialResponse(interaction: LearningInteraction): unknown {
  if (interaction.kind === "multi_select" || interaction.kind === "lead_select" || interaction.kind === "march" || interaction.kind === "hotspot_map" || interaction.kind === "model_explore") return [];
  if (interaction.kind === "sequence") return scrambledSequence(interaction);
  if (interaction.kind === "vector_lab") return { angleDeg: interaction.initialAngleDeg, predictions: {} };
  if (interaction.kind === "compare" || interaction.kind === "clinical_stage" || interaction.kind === "pairing" || interaction.kind === "categorize") return {};
  return "";
}

function responseReady(interaction: LearningInteraction, response: unknown, viewerEvidence?: ViewerTaskEvidence | null) {
  if (["point", "region", "caliper", "march"].includes(interaction.kind)) return Boolean(viewerEvidence);
  if (interaction.kind === "multi_select" || interaction.kind === "lead_select" || interaction.kind === "sequence" || interaction.kind === "hotspot_map" || interaction.kind === "model_explore") return Array.isArray(response) && response.length > 0;
  if (interaction.kind === "clinical_stage") return Object.keys((response as Record<string, string>) ?? {}).length === interaction.stages.length;
  if (interaction.kind === "compare") return Object.keys((response as Record<string, unknown>) ?? {}).length === interaction.dimensions.length;
  if (interaction.kind === "pairing") return Object.keys((response as Record<string, unknown>) ?? {}).length === interaction.left.length;
  if (interaction.kind === "categorize") return Object.keys((response as Record<string, unknown>) ?? {}).length === interaction.items.length;
  if (interaction.kind === "vector_lab") {
    const value = response && typeof response === "object" ? response as { angleDeg?: unknown; predictions?: Record<string, string> } : null;
    return Number.isFinite(Number(value?.angleDeg))
      && (interaction.predictions ?? []).every((prediction) => Boolean(value?.predictions?.[prediction.lead]));
  }
  return String(response ?? "").trim().length > 0 || typeof response === "number";
}

function InteractionInput({ interaction, response, setResponse, viewerEvidence }: {
  interaction: LearningInteraction;
  response: unknown;
  setResponse: (value: unknown) => void;
  viewerEvidence?: ViewerTaskEvidence | null;
}) {
  if (interaction.kind === "single_select") {
    return <div className="learning-option-grid">{interaction.options.map((option) => (
      <button key={option.id} className={response === option.id ? "selected" : ""} type="button" aria-pressed={response === option.id} onClick={() => setResponse(option.id)}><strong>{option.label}</strong></button>
    ))}</div>;
  }

  if (interaction.kind === "multi_select") {
    const selected = Array.isArray(response) ? response.map(String) : [];
    return <div className="learning-option-grid">{interaction.options.map((option) => {
      const active = selected.includes(option.id);
      return <button key={option.id} className={active ? "selected" : ""} type="button" aria-pressed={active} onClick={() => setResponse(active ? selected.filter((id) => id !== option.id) : [...selected, option.id])}><strong>{option.label}</strong></button>;
    })}</div>;
  }

  if (interaction.kind === "sequence") {
    const order = Array.isArray(response) ? response.map(String) : [];
    return <ol className="learning-sequence">{order.map((id, index) => {
      const card = interaction.cards.find((item) => item.id === id);
      if (!card) return null;
      const move = (delta: number) => {
        const target = index + delta;
        if (target < 0 || target >= order.length) return;
        const next = [...order];
        [next[index], next[target]] = [next[target], next[index]];
        setResponse(next);
      };
      return <li key={id}><span><b>{index + 1}</b><strong>{card.label}</strong>{card.detail ? <small>{card.detail}</small> : null}</span><span><button type="button" onClick={() => move(-1)} disabled={index === 0} aria-label={`Move ${card.label} earlier`}><ArrowUp size={15} /></button><button type="button" onClick={() => move(1)} disabled={index === order.length - 1} aria-label={`Move ${card.label} later`}><ArrowDown size={15} /></button></span></li>;
    })}</ol>;
  }

  if (interaction.kind === "lead_select") {
    const selected = Array.isArray(response) ? response.map(String) : [];
    const leads = interaction.allowedLeads ?? ALL_LEADS;
    return <div className="learning-lead-map" aria-label="12-lead selection map">{leads.map((lead) => {
      const active = selected.includes(lead);
      return <button key={lead} type="button" className={active ? "selected" : ""} aria-pressed={active} onClick={() => {
        if (interaction.selectionMode === "single") setResponse([lead]);
        else if (interaction.selectionMode === "ordered") setResponse(active ? selected.filter((item) => item !== lead) : [...selected, lead]);
        else setResponse(active ? selected.filter((item) => item !== lead) : [...selected, lead]);
      }}><strong>{lead}</strong>{interaction.selectionMode === "ordered" && active ? <small>{selected.indexOf(lead) + 1}</small> : null}</button>;
    })}</div>;
  }

  if (interaction.kind === "vector_lab") {
    const value = response && typeof response === "object" ? response as { angleDeg?: number; predictions?: Record<string, string> } : {};
    const angle = Number.isFinite(value.angleDeg) ? Number(value.angleDeg) : interaction.initialAngleDeg;
    const predictions = value.predictions ?? {};
    const setAngle = (next: number) => setResponse({ angleDeg: Math.max(-180, Math.min(180, next)), predictions });
    return <div className="learning-vector-lab"><div className="learning-vector-dial" aria-hidden="true"><span style={{ transform: `translate(-50%, -100%) rotate(${angle}deg)` }} /></div><label><span>Net vector angle</span><input aria-label={`Net vector angle toward ${interaction.targetLabel}`} aria-valuetext={`${angle} degrees`} type="range" min="-180" max="180" step="1" value={angle} onChange={(event) => setAngle(Number(event.target.value))} /><output>{angle}°</output></label><div className="learning-vector-step"><button type="button" onClick={() => setAngle(angle - 15)} aria-label="Rotate vector 15 degrees counterclockwise">−15°</button><button type="button" onClick={() => setAngle(angle + 15)} aria-label="Rotate vector 15 degrees clockwise">+15°</button></div>{interaction.predictions?.length ? <div className="learning-vector-predictions">{interaction.predictions.map((prediction) => <label key={prediction.lead}><span>{prediction.lead} dominant deflection</span><select value={predictions[prediction.lead] ?? ""} onChange={(event) => setResponse({ angleDeg: angle, predictions: { ...predictions, [prediction.lead]: event.target.value } })}><option value="">Predict polarity</option><option value="positive">Positive / upright</option><option value="negative">Negative / downward</option><option value="isoelectric">Isoelectric / small</option></select></label>)}</div> : null}<p>Target: {interaction.targetLabel}. Keyboard: Arrow keys adjust 1°; use the ±15° buttons for larger moves.</p></div>;
  }

  if (interaction.kind === "free_response") {
    return <label className="learning-response"><span>{interaction.responseLabel}</span>{interaction.sentenceFrame ? <small>{interaction.sentenceFrame}</small> : null}<textarea rows={4} value={String(response ?? "")} placeholder={interaction.placeholder} onChange={(event) => setResponse(event.target.value)} /></label>;
  }

  if (interaction.kind === "compare") {
    const answers = (response as Record<string, { left?: string; right?: string }>) ?? {};
    return <div className="learning-compare"><div className="learning-compare-head"><strong>{interaction.leftCaseConcept.replaceAll("_", " ")}</strong><strong>{interaction.rightCaseConcept.replaceAll("_", " ")}</strong></div>{interaction.dimensions.map((dimension) => <fieldset key={dimension.id}><legend>{dimension.label}</legend><input aria-label={`${dimension.label}, left case`} placeholder={`Describe ${dimension.label.toLowerCase()} on the left`} value={answers[dimension.id]?.left ?? ""} onChange={(event) => setResponse({ ...answers, [dimension.id]: { ...answers[dimension.id], left: event.target.value } })} /><input aria-label={`${dimension.label}, right case`} placeholder={`Describe ${dimension.label.toLowerCase()} on the right`} value={answers[dimension.id]?.right ?? ""} onChange={(event) => setResponse({ ...answers, [dimension.id]: { ...answers[dimension.id], right: event.target.value } })} /></fieldset>)}</div>;
  }

  if (interaction.kind === "clinical_stage") {
    const answers = (response as Record<string, string>) ?? {};
    const firstUnanswered = interaction.stages.findIndex((stage) => !answers[stage.id]);
    const visibleThrough = firstUnanswered === -1 ? interaction.stages.length - 1 : firstUnanswered;
    return <div className="learning-clinical-stages">{interaction.stages.slice(0, visibleThrough + 1).map((stage, index) => <fieldset key={stage.id} className={index === visibleThrough ? "active" : "committed"}><legend>Stage {index + 1} · {stage.heading}</legend><p>{stage.revealCopy}</p><strong>{stage.question}</strong><div className="learning-option-grid">{stage.options.map((option) => <button key={option.id} type="button" className={answers[stage.id] === option.id ? "selected" : ""} aria-pressed={answers[stage.id] === option.id} onClick={() => setResponse({ ...answers, [stage.id]: option.id })}>{option.label}</button>)}</div>{answers[stage.id] && index === visibleThrough && index < interaction.stages.length - 1 ? <p className="muted">Decision committed. The next clinical information is now available below.</p> : null}</fieldset>)}</div>;
  }

  if (interaction.kind === "hotspot_map") {
    const selected = Array.isArray(response) ? response.map(String) : [];
    const activeId = selected[selected.length - 1];
    return <div className={`learning-hotspot-map ${interaction.canvas}`} role="group" aria-label={interaction.accessibility.screenReaderSummary}>
      <MapCanvas canvas={interaction.canvas} />
      {interaction.hotspots.map((hotspot) => {
        const active = selected.includes(hotspot.id);
        const order = selected.indexOf(hotspot.id) + 1;
        return <button key={hotspot.id} type="button" className={active ? "selected" : ""} style={{ left: `${hotspot.xPercent}%`, top: `${hotspot.yPercent}%` }} aria-pressed={active} aria-label={`${hotspot.label}. ${hotspot.description}`} onClick={() => {
          if (interaction.selectionMode === "single") setResponse([hotspot.id]);
          else setResponse(active ? selected.filter((id) => id !== hotspot.id) : [...selected, hotspot.id]);
        }}><span>{interaction.selectionMode === "ordered" && active ? order : active ? "✓" : "+"}</span><strong>{hotspot.label}</strong></button>;
      })}
      <div className="learning-hotspot-readout" aria-live="polite">{activeId ? interaction.hotspots.find((hotspot) => hotspot.id === activeId)?.description : interaction.instructions}</div>
    </div>;
  }

  if (interaction.kind === "model_explore") {
    const visited = Array.isArray(response) ? response.map(String) : [];
    const activeId = visited[visited.length - 1] ?? interaction.frames[0]?.id;
    const activeIndex = Math.max(0, interaction.frames.findIndex((frame) => frame.id === activeId));
    const frame = interaction.frames[activeIndex];
    const selectFrame = (index: number) => {
      const nextFrame = interaction.frames[index];
      if (!nextFrame) return;
      setResponse(visited.includes(nextFrame.id) ? [...visited.filter((id) => id !== nextFrame.id), nextFrame.id] : [...visited, nextFrame.id]);
    };
    return <div className={`learning-model-explore ${interaction.model}`}>
      <div className="learning-model-visual" aria-hidden="true">
        <span className={`model-heart-region ${frame.activeRegion ?? "ventricles"}`} />
        {frame.vectorAngleDeg !== undefined ? <i style={{ transform: `rotate(${frame.vectorAngleDeg}deg)` }} /> : null}
        <b>{frame.waveformLabel ?? frame.label}</b>
      </div>
      <div className="learning-model-copy"><p className="eyebrow">Frame {activeIndex + 1} of {interaction.frames.length}</p><h4>{frame.label}</h4><p>{frame.narration}</p><label><span>Scrub the model</span><input type="range" min="0" max={Math.max(0, interaction.frames.length - 1)} value={activeIndex} onChange={(event) => selectFrame(Number(event.target.value))} /></label><div>{interaction.frames.map((item, index) => <button key={item.id} type="button" className={visited.includes(item.id) ? "visited" : ""} aria-pressed={item.id === frame.id} onClick={() => selectFrame(index)}>{index + 1}<span className="sr-only"> {item.label}</span></button>)}</div></div>
    </div>;
  }

  if (interaction.kind === "numeric_entry") {
    return <label className="learning-numeric-entry"><span>{interaction.label}</span><span><input type="number" min={interaction.minimum} max={interaction.maximum} step="any" value={String(response ?? "")} onChange={(event) => setResponse(event.target.value)} /><b>{interaction.unit}</b></span></label>;
  }

  if (interaction.kind === "pairing") {
    const pairs = (response as Record<string, string>) ?? {};
    return <div className="learning-pairing">{interaction.left.map((left) => <label key={left.id}><span>{left.label}</span><select value={pairs[left.id] ?? ""} onChange={(event) => setResponse({ ...pairs, [left.id]: event.target.value })}><option value="">Choose a match</option>{interaction.right.map((right) => <option key={right.id} value={right.id}>{right.label}</option>)}</select></label>)}</div>;
  }

  if (interaction.kind === "categorize") {
    const categories = (response as Record<string, string>) ?? {};
    return <div className="learning-pairing">{interaction.items.map((item) => <label key={item.id}><span>{item.label}</span><select value={categories[item.id] ?? ""} onChange={(event) => setResponse({ ...categories, [item.id]: event.target.value })}><option value="">Choose a category</option>{interaction.categories.map((category) => <option key={category.id} value={category.id}>{category.label}</option>)}</select></label>)}</div>;
  }

  if (["point", "region", "caliper", "march"].includes(interaction.kind)) {
    return <div className="learning-viewer-evidence"><strong>{viewerEvidence ? "Waveform evidence captured" : "Use the active tool on the ECG above"}</strong><span>{viewerEvidence ? summarizeViewerEvidence(viewerEvidence) : interaction.accessibility.keyboardAlternative}</span></div>;
  }

  return null;
}

function MapCanvas({ canvas }: { canvas: "torso" | "hexaxial" | "conduction_tree" | "waveform" | "heart" }) {
  if (canvas === "torso") return <svg viewBox="0 0 400 260"><path d="M146 34 Q200 2 254 34 L278 80 308 244 92 244 122 80Z" /><circle cx="200" cy="38" r="27" /><path d="M166 118 Q200 87 234 118 Q247 155 200 196 Q153 155 166 118Z" /></svg>;
  if (canvas === "hexaxial") return <svg viewBox="0 0 400 260"><circle cx="200" cy="130" r="105" /><path d="M70 130H330M200 15V245M109 78L291 182M109 182L291 78" /><circle cx="200" cy="130" r="7" /></svg>;
  if (canvas === "conduction_tree") return <svg viewBox="0 0 400 260"><path d="M201 35V98M201 98L153 158M201 98L247 158M153 158L124 224M153 158L178 224M247 158L222 224M247 158L276 224" /><circle cx="201" cy="35" r="12" /><circle cx="201" cy="98" r="10" /></svg>;
  if (canvas === "waveform") return <svg viewBox="0 0 400 260"><path d="M15 150H80Q90 145 100 150H130L145 130 160 150H185L198 185 216 55 230 168 245 150H285Q312 90 345 150H385" /></svg>;
  return <svg viewBox="0 0 400 260"><path d="M200 226C155 190 102 153 112 94 119 50 177 42 200 78 223 42 281 50 288 94 298 153 245 190 200 226Z" /><path d="M200 80V210M200 115L153 165M200 115L247 165" /></svg>;
}

function summarizeViewerEvidence(evidence: ViewerTaskEvidence) {
  if (evidence.mode === "point") return `${evidence.point.lead} at ${evidence.point.timeSec.toFixed(3)} s${evidence.feedback ? ` — ${evidence.feedback}` : ""}`;
  if (evidence.mode === "region") return `${evidence.roi.lead}, ${evidence.roi.timeStartSec.toFixed(3)}–${evidence.roi.timeEndSec.toFixed(3)} s${evidence.feedback ? ` — ${evidence.feedback}` : ""}`;
  if (evidence.mode === "caliper") return `${evidence.lead}, ${evidence.valueMs} ms`;
  return `${evidence.points.length} markers placed`;
}
