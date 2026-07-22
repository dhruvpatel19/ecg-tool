"use client";

import { ArrowDown, ArrowUp, CheckCircle2, CircleAlert, RotateCcw } from "lucide-react";
import { useEffect, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from "react";
import { feedbackFor, gradeInteraction } from "@/lib/learning/gradeInteraction";
import { evidenceRevealsSolution } from "@/lib/learning/interactionTypes";
import type { InteractionEvidence, LearningInteraction } from "@/lib/learning/interactionTypes";
import type { ViewerTaskEvidence } from "@/lib/types";
import { InteractionModelVisual } from "./InteractionModelVisual";

const ALL_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"];

type FoundationsPacketVariant = "modeled" | "guided" | "integration-one" | "integration-two";

function foundationsPacketVariant(interactionId: string): FoundationsPacketVariant | null {
  if (interactionId === "m01-s10-modeled") return "modeled";
  if (interactionId === "m01-s11-faded-sweep") return "guided";
  if (interactionId === "m01-s12-case-one") return "integration-one";
  if (interactionId === "m01-s12-case-two" || interactionId === "m01-s12-final-synthesis") return "integration-two";
  return null;
}

function foundationsPacketTrace(variant: FoundationsPacketVariant, lead: "I" | "II" | "aVF") {
  const baseline = lead === "I" ? 68 : lead === "II" ? 158 : 248;
  const beats = variant === "modeled"
    ? [96, 224, 382, 512, 688, 828, 952]
    : variant === "guided"
      ? [112, 318, 524, 730, 936]
      : variant === "integration-one"
        ? [104, 256, 408, 560, 712, 864]
        : [92, 220, 386, 506, 694, 842, 960];
  const polarity = variant === "guided"
    ? lead === "aVF" ? -0.55 : 1
    : variant === "integration-one"
      ? lead === "I" ? 1 : lead === "II" ? -0.72 : -1
      : 1;
  const pVisible = variant !== "integration-one";
  const wide = variant === "integration-one";
  const longPr = variant === "guided";
  let path = `M18 ${baseline}`;
  for (const x of beats) {
    const pCenter = x - (longPr ? 55 : 38);
    path += ` L${pCenter - 14} ${baseline}`;
    if (pVisible) {
      const pDirection = lead === "aVF" && variant === "guided" ? -1 : 1;
      path += ` Q${pCenter} ${baseline - 8 * pDirection} ${pCenter + 14} ${baseline}`;
    } else {
      path += ` L${pCenter - 6} ${baseline - 3} L${pCenter} ${baseline + 4} L${pCenter + 7} ${baseline - 2} L${pCenter + 14} ${baseline}`;
    }
    path += ` L${x - (wide ? 17 : 9)} ${baseline}`;
    if (wide) {
      path += ` L${x - 9} ${baseline + 11 * polarity} L${x + 2} ${baseline - 31 * polarity} L${x + 16} ${baseline + 24 * polarity} L${x + 28} ${baseline}`;
    } else {
      path += ` L${x - 4} ${baseline + 8 * polarity} L${x + 2} ${baseline - 34 * polarity} L${x + 9} ${baseline + 18 * polarity} L${x + 15} ${baseline}`;
    }
    const tCenter = x + (wide ? 55 : 42);
    if (variant === "integration-two" && lead === "II") {
      path += ` L${tCenter - 14} ${baseline} L${tCenter - 7} ${baseline - 4} L${tCenter} ${baseline + 5} L${tCenter + 7} ${baseline - 3} L${tCenter + 15} ${baseline}`;
    } else {
      path += ` L${tCenter - 18} ${baseline} Q${tCenter} ${baseline - 14 * polarity} ${tCenter + 20} ${baseline}`;
    }
  }
  return `${path} L982 ${baseline}`;
}

function FoundationsSweepPacket({ variant, focusLabel }: { variant: FoundationsPacketVariant; focusLabel: string }) {
  const packetLabel = variant === "modeled" ? "Packet A" : variant === "guided" ? "Packet B" : variant === "integration-one" ? "Packet C" : "Packet D";
  const patternId = `foundations-packet-grid-${variant}`;
  return (
    <section className="learning-foundations-packet" aria-label={`${packetLabel} practice ECG`}>
      <header>
        <span><strong>Practice ECG · {packetLabel}</strong> Designed for this lesson; not a patient record.</span>
        <small>Inspecting: {focusLabel}</small>
      </header>
      <svg viewBox="0 0 1000 292" role="img" aria-label={`${packetLabel}, representative leads I, II, and aVF on ECG paper. Use the waveform together with the current checkpoint evidence.`}>
        <defs>
          <pattern id={`${patternId}-minor`} width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="currentColor" strokeOpacity=".12" strokeWidth=".65" /></pattern>
          <pattern id={patternId} width="50" height="50" patternUnits="userSpaceOnUse"><rect width="50" height="50" fill={`url(#${patternId}-minor)`} /><path d="M50 0H0V50" fill="none" stroke="currentColor" strokeOpacity=".2" strokeWidth="1" /></pattern>
        </defs>
        <rect width="1000" height="292" rx="16" className="packet-paper" />
        <rect width="1000" height="292" rx="16" fill={`url(#${patternId})`} />
        {(["I", "II", "aVF"] as const).map((lead) => <g key={lead}><text x="20" y={lead === "I" ? 34 : lead === "II" ? 124 : 214}>{lead}</text><path d={foundationsPacketTrace(variant, lead)} /></g>)}
        <path className="packet-calibration" d="M20 280 H37 V260 H47 V280 H64" />
        <text className="packet-settings" x="78" y="281">25 mm/s · 10 mm/mV</text>
      </svg>
    </section>
  );
}

function checkLabel(interaction: LearningInteraction) {
  if (!interaction.id.startsWith("m01-")) return "Check answer";
  if (interaction.kind === "sequence") return "Check order";
  if (interaction.kind === "point" || interaction.kind === "region" || interaction.kind === "hotspot_map" || interaction.kind === "waveform_lab") return "Check placement";
  if (interaction.kind === "caliper" || interaction.kind === "numeric_entry") return "Check measurement";
  return "Check answer";
}

function taskLabel(interaction: LearningInteraction) {
  if (interaction.kind === "model_explore") return "Explore";
  if (interaction.kind === "sequence" || interaction.kind === "pairing" || interaction.kind === "categorize") return "Arrange";
  if (interaction.kind === "point" || interaction.kind === "region" || interaction.kind === "caliper" || interaction.kind === "march" || interaction.kind === "waveform_lab") return "ECG task";
  if (interaction.kind === "clinical_stage" && interaction.id.startsWith("m01-s10")) return "Worked example";
  if (interaction.kind === "clinical_stage" && interaction.id.startsWith("m01-s11")) return "Guided read";
  if (interaction.kind === "clinical_stage" && interaction.id.startsWith("m01-s12")) return "Complete read";
  if (interaction.kind === "clinical_stage") return "Clinical decision";
  return "Question";
}

function strongerScaffold(interaction: LearningInteraction, fallback: string) {
  if (interaction.kind === "single_select" || interaction.kind === "multi_select") return "Test each choice on its own: is it directly supported by the tracing and the question, or does it assume more than the evidence shows?";
  if (interaction.kind === "sequence") return "Anchor the first and last checkpoints, then place each middle step after the observation it depends on.";
  if (interaction.kind === "model_explore") return "Visit every numbered state and say what changed before moving to the next one.";
  if (interaction.kind === "numeric_entry" || interaction.kind === "caliper") return "Verify the ruler and both endpoints first; only then calculate the value.";
  if (interaction.kind === "point" || interaction.kind === "region" || interaction.kind === "march" || interaction.kind === "waveform_lab") return "Name the exact waveform and lead, find the nearest reliable landmark, then place the mark relative to that anchor.";
  if (interaction.kind === "compare") return "Compare one feature at a time before combining the differences into a conclusion.";
  if (interaction.kind === "free_response") return "Build the response from visible observations first, then add only the conclusion those observations support.";
  return fallback;
}

type LearningInteractionRendererProps = {
  interaction: LearningInteraction;
  packetMeasurements?: Record<string, unknown>;
  gradePacketMeasurement?: (request: {
    measurementKey: string;
    value: number;
    tolerance: number;
    derive?: "rr_from_heart_rate";
  }) => Promise<{ correct: boolean; noTarget: boolean; feedback: string }>;
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

export function LearningInteractionRenderer({ interaction, packetMeasurements, gradePacketMeasurement, viewerEvidence, onEvidence, savedEvidence }: LearningInteractionRendererProps) {
  const [attempts, setAttempts] = useState(savedEvidence?.attempts ?? 0);
  const [response, setResponse] = useState<unknown>(() => savedEvidence?.response ?? initialResponse(interaction));
  const [evidence, setEvidence] = useState<InteractionEvidence | null>(savedEvidence ?? null);
  const [inputRevision, setInputRevision] = useState(0);
  const [checking, setChecking] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    setAttempts(savedEvidence?.attempts ?? 0);
    setResponse(savedEvidence?.response ?? initialResponse(interaction));
    setEvidence(savedEvidence ?? null);
    setChecking(false);
    setServerError(null);
  }, [interaction, savedEvidence]);

  useEffect(() => {
    if (!viewerEvidence) return;
    if (interaction.kind === "point" && viewerEvidence.mode === "point") setResponse(viewerEvidence);
    if (interaction.kind === "region" && viewerEvidence.mode === "region") setResponse({ ...viewerEvidence, correct: viewerEvidence.correct });
    if (interaction.kind === "caliper" && viewerEvidence.mode === "caliper") setResponse({ ...viewerEvidence, valueMs: viewerEvidence.valueMs });
    if (interaction.kind === "march" && viewerEvidence.mode === "march") setResponse(viewerEvidence.points);
  }, [interaction.kind, viewerEvidence]);

  const feedback = evidence ? feedbackFor(interaction, evidence) : null;
  const notAssessable = evidence?.feedbackBranch === "not_assessable";
  const solutionRevealed = evidenceRevealsSolution(evidence);
  const showScaffold = attempts >= Math.max(2, interaction.maxAttemptsBeforeScaffold) && !evidence?.correct && !solutionRevealed;
  const packetVariant = foundationsPacketVariant(interaction.id);
  const packetFocus = interaction.kind === "clinical_stage"
    ? interaction.stages.find((stage) => !(response && typeof response === "object" && (response as Record<string, string>)[stage.id]))?.heading ?? "complete synthesis"
    : interaction.id === "m01-s12-case-two" ? "evidence links" : "final synthesis";

  async function submit() {
    const nextAttempts = attempts + 1;
    let serverMeasurementGrade: { correct: boolean; noTarget: boolean } | undefined;
    if (
      interaction.kind === "numeric_entry"
      && interaction.target.source === "packet_measurement"
      && interaction.target.measurementKey
      && packetMeasurements?.[interaction.target.measurementKey] === undefined
    ) {
      if (!gradePacketMeasurement) {
        setServerError("This reviewed measurement could not be checked right now. Your entry is still here.");
        return;
      }
      const value = Number(response);
      if (!Number.isFinite(value)) return;
      setChecking(true);
      setServerError(null);
      try {
        const graded = await gradePacketMeasurement({
          measurementKey: interaction.target.measurementKey,
          value,
          tolerance: interaction.target.tolerance,
          derive: interaction.target.derive,
        });
        serverMeasurementGrade = {
          correct: graded.correct,
          noTarget: graded.noTarget,
        };
      } catch {
        setServerError("The measurement check did not complete. Your entry is still here—try again.");
        return;
      } finally {
        setChecking(false);
      }
    }
    const result = gradeInteraction(interaction, response, nextAttempts, { packetMeasurements, serverMeasurementGrade });
    setAttempts(nextAttempts);
    setEvidence(result);
    onEvidence(result);
  }

  function reset() {
    setResponse(initialResponse(interaction));
    setEvidence(null);
    setInputRevision((current) => current + 1);
  }

  return (
    <section className="learning-interaction" aria-labelledby={`${interaction.id}-prompt`}>
      <header className="learning-interaction-head">
        <div>
          <p className="eyebrow">{taskLabel(interaction)}</p>
          <h3 id={`${interaction.id}-prompt`}>{interaction.prompt}</h3>
          <p>{interaction.instructions}</p>
        </div>
        <span>{solutionRevealed ? "Answer shown" : evidence?.correct ? "Complete" : `Try ${Math.min(attempts + 1, 3)} of 3`}</span>
      </header>

      <div className="learning-interaction-body">
        {packetVariant && !solutionRevealed ? <FoundationsSweepPacket variant={packetVariant} focusLabel={packetFocus} /> : null}
        {solutionRevealed
          ? <WorkedSolution interaction={interaction} />
          : <InteractionInput key={`${interaction.id}:${inputRevision}`} interaction={interaction} response={response} setResponse={setResponse} viewerEvidence={viewerEvidence} />}
        {showScaffold ? (
          <div className="learning-scaffold" role="note">
            <strong>Use this approach</strong>
            <span>{strongerScaffold(interaction, feedback?.evidenceCue ?? interaction.accessibility.instructions)}</span>
          </div>
        ) : null}
        {feedback && !solutionRevealed ? (
          <div className={`learning-branch ${notAssessable ? "partial" : evidence?.correct ? "correct" : evidence?.partial ? "partial" : "incorrect"}`} role="status" aria-live="polite">
            {evidence?.correct && !notAssessable ? <CheckCircle2 size={19} /> : <CircleAlert size={19} />}
            <span><strong>{feedback.heading}</strong>{feedback.body}{feedback.nextPrompt ? <em>{feedback.nextPrompt}</em> : null}</span>
          </div>
        ) : null}
        {evidence?.correct ? <AnswerRationaleReview interaction={interaction} response={response} /> : null}
        {serverError ? <div className="warning" role="alert">{serverError}</div> : null}
      </div>

      <footer className="learning-interaction-actions">
        {solutionRevealed
          ? <span className="muted">Review the reasoning, then continue.</span>
          : evidence?.correct
            ? <span className="muted">Answer checked</span>
            : <button className="button subtle" type="button" onClick={reset}><RotateCcw size={15} /> Clear response</button>}
        {!solutionRevealed && !evidence?.correct ? <button className="button primary" type="button" onClick={() => void submit()} disabled={checking || !responseReady(interaction, response, viewerEvidence)}>{checking ? "Checking…" : checkLabel(interaction)}</button> : null}
      </footer>
    </section>
  );
}

type WorkedSolutionRow = {
  id: string;
  label: string;
  rationale: string;
};

function workedSolutionRows(interaction: LearningInteraction): WorkedSolutionRow[] {
  if (interaction.kind === "single_select") {
    const option = interaction.options.find((item) => item.id === interaction.correctOptionId);
    return option ? [{ id: option.id, label: option.label, rationale: option.rationale }] : [];
  }
  if (interaction.kind === "multi_select") {
    return interaction.correctOptionIds.flatMap((id) => {
      const option = interaction.options.find((item) => item.id === id);
      return option ? [{ id, label: option.label, rationale: option.rationale }] : [];
    });
  }
  if (interaction.kind === "sequence") {
    return interaction.correctOrder.flatMap((id, index) => {
      const card = interaction.cards.find((item) => item.id === id);
      return card ? [{
        id,
        label: `${index + 1}. ${card.label}`,
        rationale: card.detail ?? (index === 0
          ? "Start here before depending on later interpretation steps."
          : "This step uses the evidence established before it."),
      }] : [];
    });
  }
  if (interaction.kind === "lead_select") {
    return [{
      id: "leads",
      label: interaction.correctLeads.join(interaction.selectionMode === "ordered" ? " → " : ", "),
      rationale: interaction.selectionMode === "ordered"
        ? "Use these leads in this order for the requested comparison."
        : "These are the leads that directly support the requested observation.",
    }];
  }
  if (interaction.kind === "vector_lab") {
    const predictions = (interaction.predictions ?? []).map((item) => `${item.lead}: ${item.expected}`).join(" · ");
    return [{
      id: "vector",
      label: `${interaction.targetLabel}: ${interaction.targetAngleDeg}°${predictions ? ` · ${predictions}` : ""}`,
      rationale: `Angles within ±${interaction.toleranceDeg}° support the modeled vector; lead polarity follows whether that vector points toward or away from each lead.`,
    }];
  }
  if (interaction.kind === "point") {
    return [{
      id: "point",
      label: `Mark ${interaction.concept.replaceAll("_", " ")}${interaction.allowedLeads?.length ? ` in ${interaction.allowedLeads.join(", ")}` : ""}.`,
      rationale: "Place one precise point on the requested waveform landmark.",
    }];
  }
  if (interaction.kind === "region") {
    return [{
      id: "region",
      label: `Box ${interaction.concept.replaceAll("_", " ")}${interaction.allowedLeads?.length ? ` in ${interaction.allowedLeads.join(", ")}` : ""}.`,
      rationale: `Include the whole target region${interaction.minimumDurationMs ? ` over at least ${interaction.minimumDurationMs} ms` : ""}, without substituting a nearby waveform.`,
    }];
  }
  if (interaction.kind === "caliper") {
    const knownValue = interaction.target.source === "fixed" || interaction.target.source === "authored_simulation"
      ? interaction.target.valueMs
      : undefined;
    return [{
      id: "caliper",
      label: knownValue === undefined
        ? `Measure the ${interaction.measurement.toUpperCase()} interval from its visible endpoints.`
        : `${interaction.measurement.toUpperCase()} = ${knownValue} ms`,
      rationale: `Place both interval boundaries and compare the span within ±${interaction.target.toleranceMs} ms${interaction.target.lead ? ` in ${interaction.target.lead}` : ""}.`,
    }];
  }
  if (interaction.kind === "march") {
    return [{
      id: "march",
      label: `${interaction.expectedPattern.replaceAll("_", " ")} ${interaction.target.replaceAll("_", " ")}`,
      rationale: `Mark at least ${interaction.minimumMarkers} consecutive events, then compare the intervals rather than judging spacing by eye.`,
    }];
  }
  if (interaction.kind === "compare") {
    return interaction.dimensions.map((dimension) => ({
      id: dimension.id,
      label: `${dimension.label}: ${dimension.leftAnswer} ↔ ${dimension.rightAnswer}${dimension.thirdAnswer ? ` ↔ ${dimension.thirdAnswer}` : ""}`,
      rationale: `Keep the ${[interaction.leftCaseConcept, interaction.rightCaseConcept, interaction.thirdCaseConcept].filter(Boolean).map((item) => String(item).replaceAll("_", " ")).join(", ")} evidence separate before naming the contrast.`,
    }));
  }
  if (interaction.kind === "free_response") {
    return interaction.rubric.filter((criterion) => criterion.required).map((criterion) => ({
      id: criterion.id,
      label: `${criterion.label}: ${criterion.acceptedConcepts.join(" / ")}`,
      rationale: `Include a clear statement about ${criterion.label.toLowerCase()}.`,
    }));
  }
  if (interaction.kind === "clinical_stage") {
    return interaction.stages.flatMap((stage) => {
      const option = stage.options.find((item) => stage.acceptableOptionIds.includes(item.id));
      return option ? [{
        id: stage.id,
        label: `${stage.heading}: ${option.label}`,
        rationale: option.rationale,
      }] : [];
    });
  }
  if (interaction.kind === "hotspot_map") {
    return interaction.correctHotspotIds.flatMap((id, index) => {
      const hotspot = interaction.hotspots.find((item) => item.id === id);
      return hotspot ? [{
        id,
        label: `${interaction.selectionMode === "ordered" ? `${index + 1}. ` : ""}${hotspot.label}`,
        rationale: hotspot.description,
      }] : [];
    });
  }
  if (interaction.kind === "model_explore") {
    return interaction.requiredFrameIds.flatMap((id, index) => {
      const frame = interaction.frames.find((item) => item.id === id);
      return frame ? [{ id, label: `${index + 1}. ${frame.label}`, rationale: frame.narration }] : [];
    });
  }
  if (interaction.kind === "numeric_entry") {
    const knownValue = interaction.target.source === "fixed" || interaction.target.source === "authored_simulation"
      ? interaction.target.value
      : undefined;
    return [{
      id: "numeric",
      label: knownValue === undefined
        ? `Calculate the ${interaction.label.toLowerCase()} value from the information shown.`
        : `${interaction.label}: ${knownValue} ${interaction.unit}`,
      rationale: `Use the stated ruler and endpoints; the accepted tolerance is ±${interaction.target.tolerance} ${interaction.unit}.`,
    }];
  }
  if (interaction.kind === "pairing") {
    return Object.entries(interaction.correctPairs).flatMap(([leftId, rightId]) => {
      const left = interaction.left.find((item) => item.id === leftId);
      const right = interaction.right.find((item) => item.id === rightId);
      return left && right ? [{ id: leftId, label: `${left.label} → ${right.label}`, rationale: "This is the supported match." }] : [];
    });
  }
  if (interaction.kind === "categorize") {
    return Object.entries(interaction.correctCategoryByItem).flatMap(([itemId, categoryId]) => {
      const item = interaction.items.find((candidate) => candidate.id === itemId);
      const category = interaction.categories.find((candidate) => candidate.id === categoryId);
      return item && category ? [{ id: itemId, label: `${item.label} → ${category.label}`, rationale: "This category matches the ECG finding and the conclusion it supports." }] : [];
    });
  }
  const requiredTargets = interaction.requiredTargetIds
    .map((id) => interaction.targets.find((target) => target.id === id))
    .filter((target): target is NonNullable<typeof target> => Boolean(target));
  if (interaction.task === "point_targets") {
    return requiredTargets.map((target) => ({
      id: target.id,
      label: `${target.label}: ${target.timeMs ?? "correct landmark"}${target.timeMs === undefined ? "" : " ms"}`,
      rationale: `Place the marker within ±${interaction.toleranceMs} ms of the modeled landmark.`,
    }));
  }
  if (interaction.task === "interval" || interaction.task === "region") {
    return requiredTargets.map((target) => ({
      id: target.id,
      label: target.startMs !== undefined && target.endMs !== undefined
        ? `${target.label}: ${target.startMs}–${target.endMs} ms`
        : target.label,
      rationale: `Set both boundaries within ±${interaction.toleranceMs} ms of the modeled region.`,
    }));
  }
  return [{
    id: "waveform-march",
    label: `${interaction.expectedPattern ?? "Correct"} pattern · ${requiredTargets.map((target) => target.timeMs).filter((value) => value !== undefined).join(", ")} ms`,
    rationale: `Mark ${interaction.minimumMarkers ?? requiredTargets.length} consecutive events within ±${interaction.toleranceMs} ms, then compare their intervals.`,
  }];
}

function WorkedSolution({ interaction }: { interaction: LearningInteraction }) {
  const rows = workedSolutionRows(interaction);
  return <section className="learning-answer-review" aria-label="Worked solution">
    <header>
      <strong>Here’s the answer</strong>
      <span>Compare each step with your reasoning. You can continue after reviewing it, and this topic will stay available for more practice.</span>
    </header>
    <div>{rows.map((row) => <article key={row.id} data-status="supported">
      <CheckCircle2 size={16} />
      <span><small>Answer</small><strong>{row.label}</strong><p>{row.rationale}</p></span>
    </article>)}</div>
  </section>;
}

function AnswerRationaleReview({ interaction, response }: {
  interaction: LearningInteraction;
  response: unknown;
}) {
  const rows: Array<{ id: string; status: "supported" | "revise" | "missed"; label: string; rationale: string }> = [];
  if (interaction.kind === "single_select") {
    const selectedId = String(response ?? "");
    const selected = interaction.options.find((option) => option.id === selectedId);
    const correct = interaction.options.find((option) => option.id === interaction.correctOptionId);
    if (selected) rows.push({
      id: `selected-${selected.id}`,
      status: selected.id === interaction.correctOptionId ? "supported" : "revise",
      label: selected.label,
      rationale: selected.rationale,
    });
    if (correct && correct.id !== selected?.id) rows.push({
      id: `correct-${correct.id}`,
      status: "missed",
      label: correct.label,
      rationale: correct.rationale,
    });
  } else if (interaction.kind === "multi_select") {
    const selectedIds = new Set(Array.isArray(response) ? response.map(String) : []);
    const correctIds = new Set(interaction.correctOptionIds);
    interaction.options.forEach((option) => {
      if (selectedIds.has(option.id)) rows.push({
        id: `selected-${option.id}`,
        status: correctIds.has(option.id) ? "supported" : "revise",
        label: option.label,
        rationale: option.rationale,
      });
      else if (correctIds.has(option.id)) rows.push({
        id: `missed-${option.id}`,
        status: "missed",
        label: option.label,
        rationale: option.rationale,
      });
    });
  } else if (interaction.kind === "clinical_stage") {
    const answers = response && typeof response === "object" ? response as Record<string, string> : {};
    interaction.stages.forEach((stage) => {
      const selected = stage.options.find((option) => option.id === answers[stage.id]);
      const acceptable = stage.options.find((option) => stage.acceptableOptionIds.includes(option.id));
      if (selected) rows.push({
        id: `${stage.id}-selected-${selected.id}`,
        status: stage.acceptableOptionIds.includes(selected.id) ? "supported" : "revise",
        label: `${stage.heading}: ${selected.label}`,
        rationale: selected.rationale,
      });
      if (acceptable && acceptable.id !== selected?.id) rows.push({
        id: `${stage.id}-missed-${acceptable.id}`,
        status: "missed",
        label: `${stage.heading}: ${acceptable.label}`,
        rationale: acceptable.rationale,
      });
    });
  } else if (interaction.kind === "compare") {
    const answers = response && typeof response === "object" ? response as Record<string, { left?: string; right?: string; third?: string }> : {};
    interaction.dimensions.forEach((dimension) => {
      const selected = answers[dimension.id];
      const cells = [
        `${interaction.leftCaseConcept.replaceAll("_", " ")}: ${selected?.left ?? "—"}`,
        `${interaction.rightCaseConcept.replaceAll("_", " ")}: ${selected?.right ?? "—"}`,
        ...(interaction.thirdCaseConcept ? [`${interaction.thirdCaseConcept.replaceAll("_", " ")}: ${selected?.third ?? "—"}`] : []),
      ];
      rows.push({
        id: dimension.id,
        status: "supported",
        label: `${dimension.label} · ${cells.join(" · ")}`,
        rationale: "This row keeps each observation attached to its own evidence category before the pattern is synthesized.",
      });
    });
  }
  if (!rows.length) return null;
  return <section className="learning-answer-review" aria-label="Answer reasoning">
    <header><strong>Answer reasoning</strong><span>Review the evidence, then revise only what changed the conclusion.</span></header>
    <div>{rows.map((row) => <article key={row.id} data-status={row.status}>
      {row.status === "supported" ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}
      <span><small>{row.status === "supported" ? "Supported" : row.status === "missed" ? "Best-supported answer" : "Revise this choice"}</small><strong>{row.label}</strong><p>{row.rationale}</p></span>
    </article>)}</div>
  </section>;
}

function initialResponse(interaction: LearningInteraction): unknown {
  if (interaction.kind === "multi_select" || interaction.kind === "lead_select" || interaction.kind === "march" || interaction.kind === "hotspot_map" || interaction.kind === "model_explore") return [];
  if (interaction.kind === "waveform_lab") return interaction.task === "march" ? [] : {};
  if (interaction.kind === "sequence") return scrambledSequence(interaction);
  if (interaction.kind === "vector_lab") return { angleDeg: interaction.initialAngleDeg, predictions: {} };
  if (interaction.kind === "compare" || interaction.kind === "clinical_stage" || interaction.kind === "pairing" || interaction.kind === "categorize") return {};
  return "";
}

function responseReady(interaction: LearningInteraction, response: unknown, viewerEvidence?: ViewerTaskEvidence | null) {
  if (["point", "region", "caliper", "march"].includes(interaction.kind)) return Boolean(viewerEvidence);
  if (interaction.kind === "multi_select" || interaction.kind === "lead_select" || interaction.kind === "sequence" || interaction.kind === "hotspot_map") return Array.isArray(response) && response.length > 0;
  if (interaction.kind === "model_explore") {
    const visited = new Set(Array.isArray(response) ? response.map(String) : []);
    return interaction.requiredFrameIds.every((id) => visited.has(id));
  }
  if (interaction.kind === "clinical_stage") return Object.keys((response as Record<string, string>) ?? {}).length === interaction.stages.length;
  if (interaction.kind === "compare") {
    const answers = response && typeof response === "object" ? response as Record<string, { left?: string; right?: string; third?: string }> : {};
    return interaction.dimensions.every((dimension) => Boolean(
      answers[dimension.id]?.left
      && answers[dimension.id]?.right
      && (!interaction.thirdCaseConcept || answers[dimension.id]?.third),
    ));
  }
  if (interaction.kind === "pairing") return Object.keys((response as Record<string, unknown>) ?? {}).length === interaction.left.length;
  if (interaction.kind === "categorize") return Object.keys((response as Record<string, unknown>) ?? {}).length === interaction.items.length;
  if (interaction.kind === "waveform_lab") {
    if (interaction.task === "march") return Array.isArray(response) && response.length >= (interaction.minimumMarkers ?? 1);
    if (interaction.task === "point_targets") {
      const points = response && typeof response === "object" ? response as Record<string, unknown> : {};
      return interaction.requiredTargetIds.every((id) => Number.isFinite(Number(points[id])));
    }
    const boundaries = response && typeof response === "object" ? response as { startMs?: unknown; endMs?: unknown } : {};
    return Number.isFinite(Number(boundaries.startMs)) && Number.isFinite(Number(boundaries.endMs));
  }
  if (interaction.kind === "vector_lab") {
    const value = response && typeof response === "object" ? response as { angleDeg?: unknown; predictions?: Record<string, string> } : null;
    return Number.isFinite(Number(value?.angleDeg))
      && (interaction.predictions ?? []).every((prediction) => Boolean(value?.predictions?.[prediction.lead]));
  }
  return String(response ?? "").trim().length > 0 || typeof response === "number";
}

function modelPredictionPrompt(model: Extract<LearningInteraction, { kind: "model_explore" }>["model"]) {
  if (model === "cardiac_cycle") return "Which electrical event should dominate this state?";
  if (model === "vector_projection") return "How should the net vector project onto the lead axis?";
  if (model === "av_ladder") return "What should happen to the next atrial impulse?";
  if (model === "bundle_activation") return "Which ventricular activation pattern should appear?";
  if (model === "reentry") return "What should the impulse do at this point in the circuit?";
  return "Which surface-trace consequence should become most important?";
}

function modelPredictionOptions(model: Extract<LearningInteraction, { kind: "model_explore" }>["model"]) {
  if (model === "cardiac_cycle") return ["Atrial activation", "AV / His-Purkinje conduction", "Ventricular activation or recovery"];
  if (model === "vector_projection") return ["Positive projection", "Negative projection", "Near-isoelectric projection"];
  if (model === "av_ladder") return ["Conducts to the ventricle", "Blocks before the ventricle", "Atria and ventricles dissociate"];
  if (model === "bundle_activation") return ["Near-synchronous activation", "Right ventricular activation is late", "Left ventricular activation is late"];
  if (model === "reentry") return ["The circuit terminates", "The impulse continues around the loop", "The impulse returns retrograde"];
  return ["Activation interval / QRS", "ST–T recovery morphology", "QT duration or correction"];
}

function ModelExploreInput({ interaction, response, setResponse }: {
  interaction: Extract<LearningInteraction, { kind: "model_explore" }>;
  response: unknown;
  setResponse: (value: unknown) => void;
}) {
  const visited = Array.isArray(response) ? response.map(String) : [];
  const lastVisitedIndex = Math.max(0, interaction.frames.findIndex((frame) => frame.id === visited[visited.length - 1]));
  const [activeIndex, setActiveIndex] = useState(lastVisitedIndex);
  const [predictions, setPredictions] = useState<Record<string, string>>({});
  const frame = interaction.frames[activeIndex] ?? interaction.frames[0];
  const revealed = Boolean(frame && visited.includes(frame.id));
  const requiredVisited = interaction.requiredFrameIds.filter((id) => visited.includes(id)).length;

  useEffect(() => {
    setActiveIndex(Math.max(0, interaction.frames.findIndex((item) => item.id === visited[visited.length - 1])));
    setPredictions({});
    // Reset only when the authored model changes. Response updates should not
    // move the learner away from the state they just revealed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interaction.id]);

  if (!frame) return null;
  const revealFrame = () => {
    if (!predictions[frame.id] || revealed) return;
    setResponse([...visited, frame.id]);
  };
  const nextRequiredIndex = interaction.frames.findIndex((item) => interaction.requiredFrameIds.includes(item.id) && !visited.includes(item.id));
  const advance = () => setActiveIndex(nextRequiredIndex >= 0 ? nextRequiredIndex : Math.min(interaction.frames.length - 1, activeIndex + 1));

  return <div className={`learning-model-explore ${interaction.model}`}>
    <InteractionModelVisual model={interaction.model} frame={frame} frameIndex={activeIndex} frameCount={interaction.frames.length} concealed={!revealed} />
    <section className="learning-model-copy" aria-label="Mechanism exploration controls">
      <div className="learning-model-progress"><span>Mechanism lab</span><strong>{requiredVisited}/{interaction.requiredFrameIds.length} required states investigated</strong></div>
      <div className="learning-model-tabs" role="tablist" aria-label="Model states">
        {interaction.frames.map((item, index) => <button key={item.id} type="button" role="tab" aria-selected={index === activeIndex} className={`${index === activeIndex ? "active" : ""} ${visited.includes(item.id) ? "visited" : ""}`} onClick={() => setActiveIndex(index)}><span>{visited.includes(item.id) ? "✓" : index + 1}</span>{item.label}</button>)}
      </div>
      <label className="learning-model-scrubber"><span>Scrub between states</span><input type="range" min="0" max={Math.max(0, interaction.frames.length - 1)} value={activeIndex} aria-valuetext={frame.label} onChange={(event) => setActiveIndex(Number(event.target.value))} /></label>
      <div className="learning-model-state">
        <p className="eyebrow">State {activeIndex + 1} of {interaction.frames.length}</p>
        <h4>{frame.label}</h4>
        {!revealed ? <fieldset className="learning-model-prediction">
          <legend>Predict before reveal</legend>
          <p>{modelPredictionPrompt(interaction.model)}</p>
          <div>{modelPredictionOptions(interaction.model).map((option) => <button key={option} type="button" aria-pressed={predictions[frame.id] === option} className={predictions[frame.id] === option ? "selected" : ""} onClick={() => setPredictions({ ...predictions, [frame.id]: option })}>{option}</button>)}</div>
          <button className="button primary small" type="button" disabled={!predictions[frame.id]} onClick={revealFrame}>Reveal mechanism</button>
        </fieldset> : <div className="learning-model-reveal" aria-live="polite">
          <span>Your prediction · {predictions[frame.id] ?? "reviewed state"}</span>
          <p>{frame.narration}</p>
          {requiredVisited < interaction.requiredFrameIds.length ? <button className="button small" type="button" onClick={advance}>Investigate next required state</button> : <strong>All required states investigated. Now check the mechanism.</strong>}
        </div>}
      </div>
    </section>
  </div>;
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
    const answers = (response as Record<string, { left?: string; right?: string; third?: string }>) ?? {};
    const columns = [
      { key: "left" as const, label: interaction.leftCaseConcept.replaceAll("_", " ") },
      { key: "right" as const, label: interaction.rightCaseConcept.replaceAll("_", " ") },
      ...(interaction.thirdCaseConcept ? [{ key: "third" as const, label: interaction.thirdCaseConcept.replaceAll("_", " ") }] : []),
    ];
    return <div className={`learning-compare ${columns.length === 3 ? "has-three" : ""}`}>
      <div className="learning-compare-boundary"><strong>Authored evidence board</strong><span>Assign each observation before combining the pattern. This board does not itself supply another patient tracing.</span></div>
      <div className="learning-compare-scroll"><table style={{ "--compare-columns": columns.length } as CSSProperties}>
        <caption className="sr-only">Assign one authored evidence observation to each comparison category for every row.</caption>
        <thead><tr><th scope="col">Evidence row</th>{columns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>{interaction.dimensions.map((dimension, rowIndex) => {
          const options = Array.from(new Set([dimension.leftAnswer, dimension.rightAnswer, dimension.thirdAnswer, "Not assessable from the supplied evidence"].filter(Boolean) as string[]));
          return <tr key={dimension.id}>
            <th scope="row"><span>{rowIndex + 1}</span>{dimension.label}</th>
            {columns.map((column) => <td key={column.key}><select aria-label={`${dimension.label}, ${column.label}`} value={answers[dimension.id]?.[column.key] ?? ""} onChange={(event) => setResponse({ ...answers, [dimension.id]: { ...answers[dimension.id], [column.key]: event.target.value } })}><option value="">Assign the evidence</option>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select></td>)}
          </tr>;
        })}</tbody>
      </table></div>
    </div>;
  }

  if (interaction.kind === "clinical_stage") {
    return <ClinicalStageInput interaction={interaction} response={response} setResponse={setResponse} />;
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
    return <ModelExploreInput interaction={interaction} response={response} setResponse={setResponse} />;
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

  if (interaction.kind === "waveform_lab") {
    return <WaveformLabInput interaction={interaction} response={response} setResponse={setResponse} />;
  }

  if (["point", "region", "caliper", "march"].includes(interaction.kind)) {
    return <div className="learning-viewer-evidence"><strong>{viewerEvidence ? "Waveform evidence captured" : "Use the active tool on the ECG above"}</strong><span>{viewerEvidence ? summarizeViewerEvidence(viewerEvidence) : interaction.accessibility.keyboardAlternative}</span></div>;
  }

  return null;
}

const WAVEFORM_COLORS = ["#1d4ed8", "#0f766e", "#9333ea", "#b45309", "#be123c", "#0369a1"];

function gaussian(time: number, center: number, width: number, amplitude: number) {
  const distance = (time - center) / width;
  return amplitude * Math.exp(-(distance * distance));
}

function beatValue(time: number, center: number, trace: Extract<LearningInteraction, { kind: "waveform_lab" }>["trace"]) {
  const longPr = trace === "long_pr_beat";
  const wide = trace === "wide_qrs_beat";
  const stT = trace === "st_t_beat";
  const pCenter = center - (longPr ? 300 : 190);
  const qrsWidth = wide ? 42 : 18;
  const qrs = gaussian(time, center - qrsWidth * 0.8, qrsWidth * 0.55, -0.22)
    + gaussian(time, center, qrsWidth * 0.38, 1.35)
    + gaussian(time, center + qrsWidth * 0.9, qrsWidth * 0.55, -0.48);
  const stShift = stT && time > center + qrsWidth * 1.5 && time < center + 190 ? 0.16 : 0;
  // Keep the authored complexes inside the calibrated paper window. The
  // calibration pulse remains exactly 1 mV; the teaching beat peaks at about
  // 0.7 mV so both can be rendered at the declared gain without clipping.
  return 0.52 * (gaussian(time, pCenter, 38, 0.18)
    + qrs
    + stShift
    + gaussian(time, center + 285, 78, stT ? -0.32 : 0.42));
}

function authoredTraceValue(interaction: Extract<LearningInteraction, { kind: "waveform_lab" }>, time: number) {
  if (interaction.trace === "calibration_beat" && time < 260) {
    if (time < 40 || time > 240) return 0;
    return 1;
  }
  let centers: number[];
  if (interaction.trace === "regular_strip" || interaction.trace === "artifact_strip") centers = [450, 1250, 2050, 2850, 3650, 4450, 5250];
  else if (interaction.trace === "irregular_strip") centers = [380, 1050, 1840, 2500, 3440, 4170, 5070, 5750];
  else centers = [interaction.trace === "alternate_beat" ? 430 : interaction.trace === "calibration_beat" ? 560 : 440];
  let value = centers.reduce((sum, center) => sum + beatValue(time, center, interaction.trace), 0);
  if (interaction.trace === "artifact_strip" && time > 2050 && time < 3220) {
    value += Math.sin(time / 7) * 0.38 + Math.sin(time / 19) * 0.24;
  }
  return value;
}

function authoredTraceGeometry(interaction: Extract<LearningInteraction, { kind: "waveform_lab" }>) {
  // The plotted region is 900 SVG units wide. Paper speed determines how many
  // 1 mm horizontal boxes fit in the requested time window; gain determines
  // the vertical scale. Keeping both axes on the same millimetre scale makes
  // the grid a real ruler instead of decorative ECG paper.
  const smallBoxPx = 900_000 / (interaction.durationMs * interaction.paperSpeedMmSec);
  const amplitudePxPerMv = smallBoxPx * interaction.gainMmMv;
  const singleBeat = interaction.durationMs <= 1_500;
  const canvasHeight = singleBeat
    ? Math.max(520, Math.ceil(amplitudePxPerMv * 1.45 + 120))
    : 300;
  const baselineY = singleBeat
    ? Math.min(canvasHeight - 90, 60 + amplitudePxPerMv)
    : Math.round(canvasHeight * 0.55);
  return {
    smallBoxPx,
    largeBoxPx: smallBoxPx * 5,
    amplitudePxPerMv,
    canvasHeight,
    baselineY,
  };
}

function authoredTracePath(interaction: Extract<LearningInteraction, { kind: "waveform_lab" }>) {
  const geometry = authoredTraceGeometry(interaction);
  const samples = Math.max(280, Math.min(900, Math.round(interaction.durationMs / 7)));
  return Array.from({ length: samples + 1 }, (_, index) => {
    const time = (interaction.durationMs * index) / samples;
    const x = 60 + (900 * time) / interaction.durationMs;
    const y = geometry.baselineY - authoredTraceValue(interaction, time) * geometry.amplitudePxPerMv;
    return `${index ? "L" : "M"}${x.toFixed(1)} ${Math.max(18, Math.min(geometry.canvasHeight - 18, y)).toFixed(1)}`;
  }).join(" ");
}

function WaveformLabInput({ interaction, response, setResponse }: {
  interaction: Extract<LearningInteraction, { kind: "waveform_lab" }>;
  response: unknown;
  setResponse: (value: unknown) => void;
}) {
  const [cursorMs, setCursorMs] = useState(Math.round(interaction.durationMs / 2));
  const [activeTargetId, setActiveTargetId] = useState(interaction.requiredTargetIds[0] ?? "");
  const geometry = authoredTraceGeometry(interaction);
  const pointResponse = response && typeof response === "object" && !Array.isArray(response)
    ? response as Record<string, number>
    : {};
  const boundaryResponse = response && typeof response === "object" && !Array.isArray(response)
    ? response as { startMs?: number; endMs?: number }
    : {};
  const markers = Array.isArray(response) ? response.map(Number).filter(Number.isFinite) : [];

  const timeFromEvent = (event: ReactMouseEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - bounds.left) / Math.max(bounds.width, 1)) * 1000;
    return Math.round(Math.max(0, Math.min(interaction.durationMs, ((viewX - 60) / 900) * interaction.durationMs)));
  };
  const commitCursor = (timeMs: number) => {
    setCursorMs(timeMs);
    if (interaction.task === "point_targets") {
      if (!activeTargetId) return;
      setResponse({ ...pointResponse, [activeTargetId]: timeMs });
      const next = interaction.requiredTargetIds.find((id) => id !== activeTargetId && !Number.isFinite(Number(pointResponse[id])));
      if (next) setActiveTargetId(next);
      return;
    }
    if (interaction.task === "march") {
      const closeIndex = markers.findIndex((marker) => Math.abs(marker - timeMs) <= Math.max(25, interaction.toleranceMs / 2));
      setResponse(closeIndex >= 0 ? markers.filter((_, index) => index !== closeIndex) : [...markers, timeMs].sort((a, b) => a - b));
      return;
    }
    if (!Number.isFinite(Number(boundaryResponse.startMs)) || Number.isFinite(Number(boundaryResponse.endMs))) {
      setResponse({ startMs: timeMs });
    } else {
      setResponse({ startMs: boundaryResponse.startMs, endMs: timeMs });
    }
  };
  const positioned = interaction.task === "march"
    ? markers.map((timeMs, index) => ({ id: `marker-${index}`, label: `${index + 1}`, timeMs, color: WAVEFORM_COLORS[0] }))
    : interaction.task === "point_targets"
      ? interaction.requiredTargetIds.flatMap((id, index) => Number.isFinite(Number(pointResponse[id])) ? [{ id, label: interaction.targets.find((target) => target.id === id)?.label ?? id, timeMs: Number(pointResponse[id]), color: WAVEFORM_COLORS[index % WAVEFORM_COLORS.length] }] : [])
      : [boundaryResponse.startMs, boundaryResponse.endMs].flatMap((timeMs, index) => Number.isFinite(Number(timeMs)) ? [{ id: index ? "end" : "start", label: index ? "End" : "Start", timeMs: Number(timeMs), color: WAVEFORM_COLORS[index] }] : []);
  const selectedSpan = interaction.task === "interval" || interaction.task === "region"
    ? Number.isFinite(Number(boundaryResponse.startMs)) && Number.isFinite(Number(boundaryResponse.endMs))
      ? { start: Math.min(Number(boundaryResponse.startMs), Number(boundaryResponse.endMs)), end: Math.max(Number(boundaryResponse.startMs), Number(boundaryResponse.endMs)) }
      : null
    : null;

  return <div className="learning-waveform-lab">
    <div className="learning-waveform-meta">
      <span><strong>Practice waveform</strong> · {interaction.lead}</span>
      <span>{interaction.paperSpeedMmSec} mm/s · {interaction.gainMmMv} mm/mV</span>
    </div>
    <svg viewBox={`0 0 1000 ${geometry.canvasHeight}`} role="img" aria-label={`${interaction.lead} practice ECG waveform. ${interaction.accessibility.screenReaderSummary}`} onClick={(event) => commitCursor(timeFromEvent(event))}>
      <defs><pattern id={`small-grid-${interaction.id}`} width={geometry.smallBoxPx} height={geometry.smallBoxPx} patternUnits="userSpaceOnUse"><path d={`M${geometry.smallBoxPx} 0H0V${geometry.smallBoxPx}`} fill="none" stroke="currentColor" strokeOpacity=".12" strokeWidth="1" /></pattern><pattern id={`large-grid-${interaction.id}`} width={geometry.largeBoxPx} height={geometry.largeBoxPx} patternUnits="userSpaceOnUse"><rect width={geometry.largeBoxPx} height={geometry.largeBoxPx} fill={`url(#small-grid-${interaction.id})`} /><path d={`M${geometry.largeBoxPx} 0H0V${geometry.largeBoxPx}`} fill="none" stroke="currentColor" strokeOpacity=".2" strokeWidth="1.5" /></pattern></defs>
      <rect x="0" y="0" width="1000" height={geometry.canvasHeight} rx="16" className="waveform-paper" />
      <rect x="0" y="0" width="1000" height={geometry.canvasHeight} rx="16" fill={`url(#large-grid-${interaction.id})`} />
      {selectedSpan ? <rect className="waveform-selection" x={60 + 900 * selectedSpan.start / interaction.durationMs} y="18" width={Math.max(2, 900 * (selectedSpan.end - selectedSpan.start) / interaction.durationMs)} height={geometry.canvasHeight - 36} rx="5" /> : null}
      <path className="waveform-trace" d={authoredTracePath(interaction)} />
      {positioned.map((marker) => {
        const x = 60 + 900 * marker.timeMs / interaction.durationMs;
        return <g key={marker.id} className="waveform-marker" style={{ color: marker.color }}><line x1={x} y1="18" x2={x} y2={geometry.canvasHeight - 18} /><circle cx={x} cy="30" r="10" /><text x={x} y="34" textAnchor="middle">{marker.label.slice(0, 1)}</text></g>;
      })}
      <line className="waveform-cursor" x1={60 + 900 * cursorMs / interaction.durationMs} y1="18" x2={60 + 900 * cursorMs / interaction.durationMs} y2={geometry.canvasHeight - 18} />
      <text x="20" y="30" className="waveform-lead-label">{interaction.lead}</text>
    </svg>
    <div className="learning-waveform-controls">
      <label><span>Keyboard cursor</span><input type="range" min="0" max={interaction.durationMs} step="10" value={cursorMs} onChange={(event) => setCursorMs(Number(event.target.value))} /><output>{cursorMs} ms</output></label>
      {interaction.task === "point_targets" ? <label><span>Target to mark</span><select value={activeTargetId} onChange={(event) => setActiveTargetId(event.target.value)}>{interaction.requiredTargetIds.map((id) => <option key={id} value={id}>{interaction.targets.find((target) => target.id === id)?.label ?? id}</option>)}</select></label> : null}
      <button className="button small" type="button" onClick={() => commitCursor(cursorMs)}>{interaction.task === "march" ? "Toggle marker" : interaction.task === "point_targets" ? "Place target" : Number.isFinite(Number(boundaryResponse.startMs)) && !Number.isFinite(Number(boundaryResponse.endMs)) ? "Place end" : "Place start"}</button>
      {(interaction.task === "interval" || interaction.task === "region") && selectedSpan ? <span className="learning-waveform-readout">Selected span <strong>{Math.round(selectedSpan.end - selectedSpan.start)} ms</strong></span> : null}
      {interaction.task === "march" ? <span className="learning-waveform-readout"><strong>{markers.length}</strong> markers placed</span> : null}
    </div>
    <p className="learning-waveform-boundary"><strong>Practice waveform:</strong> this example is designed to teach the technique. It is not a patient ECG.</p>
  </div>;
}

function ClinicalStageInput({ interaction, response, setResponse }: {
  interaction: Extract<LearningInteraction, { kind: "clinical_stage" }>;
  response: unknown;
  setResponse: (value: unknown) => void;
}) {
  const answers = response && typeof response === "object"
    ? response as Record<string, string>
    : {};
  const firstUnanswered = interaction.stages.findIndex((stage) => !answers[stage.id]);
  const activeIndex = firstUnanswered === -1 ? interaction.stages.length : firstUnanswered;
  const [draftChoice, setDraftChoice] = useState({ stageId: "", optionId: "" });
  const isFoundationsRead = interaction.id.startsWith("m01-");

  const visibleStages = interaction.stages.slice(0, Math.min(activeIndex + 1, interaction.stages.length));
  return <div className="learning-clinical-stages">
    {visibleStages.map((stage, index) => {
      const committedOptionId = answers[stage.id];
      const committed = Boolean(committedOptionId);
      const active = index === activeIndex && !committed;
      const draftOptionId = active && draftChoice.stageId === stage.id ? draftChoice.optionId : "";
      const selectedOptionId = committedOptionId || draftOptionId;
      return <fieldset key={stage.id} className={active ? "active" : "committed"} disabled={committed}>
        <legend>{isFoundationsRead ? "Checkpoint" : "Stage"} {index + 1} · {stage.heading}</legend>
        <p>{stage.revealCopy}</p>
        <strong>{stage.question}</strong>
        <div className="learning-option-grid">
          {stage.options.map((option) => <button
            key={option.id}
            type="button"
            disabled={committed}
            className={selectedOptionId === option.id ? "selected" : ""}
            aria-pressed={selectedOptionId === option.id}
            onClick={() => setDraftChoice({ stageId: stage.id, optionId: option.id })}
          >{option.label}</button>)}
        </div>
        {active ? <button
          className="button primary small learning-stage-commit"
          type="button"
          disabled={!draftOptionId}
          onClick={() => setResponse({ ...answers, [stage.id]: draftOptionId })}
        >{isFoundationsRead
          ? index === interaction.stages.length - 1 ? "Finish this read" : "Choose and continue"
          : index === interaction.stages.length - 1 ? "Commit final stage" : "Commit stage and reveal next"}</button> : null}
        {committed ? <p className="muted" role="status">{isFoundationsRead ? "Response saved. Your earlier reasoning stays visible." : "Decision committed. This stage is locked."}</p> : null}
      </fieldset>;
    })}
    {firstUnanswered === -1 ? <p className="muted" role="status">{isFoundationsRead ? "Every checkpoint is answered. Review the complete read, then check your reasoning." : "All staged decisions are committed. Check your evidence when ready."}</p> : null}
  </div>;
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
