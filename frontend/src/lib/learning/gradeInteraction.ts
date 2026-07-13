import type {
  CaliperInteraction,
  FeedbackBranch,
  InteractionEvidence,
  LearningInteraction,
  MarchInteraction,
  NumericEntryInteraction,
} from "@/lib/learning/interactionTypes";
import type { ECGPoint } from "@/lib/coordinates";

type GradeContext = {
  packetMeasurements?: Record<string, unknown>;
};

const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const SEMANTIC_EQUIVALENTS: Record<string, string[]> = {
  same: ["single", "one", "shared"],
  event: ["activation", "depolarization", "electrical activity", "heartbeat", "electrical process"],
  different: ["distinct", "varied", "unique", "multiple"],
  views: ["viewpoints", "perspectives", "angles", "directions", "orientations", "projections"],
  view: ["viewpoint", "perspective", "angle", "direction", "orientation", "projection"],
  positive: ["up", "upright"],
  negative: ["down", "downward"],
  wide: ["broad", "prolonged"],
  narrow: ["normal duration", "not wide"],
  opposite: ["discordant", "away"],
  discordant: ["opposite"],
  concordant: ["same direction", "aligned"],
  unavailable: ["not assessable", "missing", "cannot assess"],
  absent: ["not present", "none"],
  present: ["seen", "visible"],
  regular: ["even", "constant"],
  variable: ["changing", "irregular"],
};

const SEMANTIC_STOP_WORDS = new Set(["a", "an", "and", "as", "by", "for", "in", "is", "of", "or", "the", "to", "with", "often", "may"]);

function semanticFieldScore(answer: string, expected: string): number {
  const actual = normalize(answer);
  const target = normalize(expected);
  if (!actual) return 0;
  if (actual === target || actual.includes(target) || target.includes(actual) && actual.length >= 4) return 1;
  const expandedActual = new Set(actual.split(" "));
  for (const [canonical, equivalents] of Object.entries(SEMANTIC_EQUIVALENTS)) {
    if (expandedActual.has(canonical) || equivalents.some((equivalent) => actual.includes(equivalent))) {
      expandedActual.add(canonical);
      equivalents.forEach((equivalent) => normalize(equivalent).split(" ").forEach((token) => expandedActual.add(token)));
    }
  }
  const targetTokens = target.split(" ").filter((token) => token.length > 1 && !SEMANTIC_STOP_WORDS.has(token));
  if (!targetTokens.length) return 0;
  const hits = targetTokens.filter((token) => expandedActual.has(token)
    || (SEMANTIC_EQUIVALENTS[token] ?? []).some((equivalent) => actual.includes(equivalent))).length;
  return hits / targetTokens.length;
}

function circularDifference(a: number, b: number) {
  return Math.abs((((a - b) % 360) + 540) % 360 - 180);
}

function numericMeasurement(interaction: CaliperInteraction | NumericEntryInteraction, context: GradeContext): number | null {
  if (interaction.target.source === "fixed" || interaction.target.source === "authored_simulation") {
    if ("valueMs" in interaction.target) return interaction.target.valueMs ?? null;
    if ("value" in interaction.target) return interaction.target.value ?? null;
    return null;
  }
  const raw = interaction.target.measurementKey
    ? context.packetMeasurements?.[interaction.target.measurementKey]
    : undefined;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    if (interaction.target.derive === "rr_from_heart_rate") return 60_000 / raw;
    return raw;
  }
  if (raw && typeof raw === "object") {
    const candidate = (raw as Record<string, unknown>).value ?? (raw as Record<string, unknown>).value_ms;
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      if (interaction.target.derive === "rr_from_heart_rate") return 60_000 / candidate;
      return candidate;
    }
  }
  return null;
}

function gradeMarch(interaction: MarchInteraction, points: ECGPoint[]) {
  if (points.length < interaction.minimumMarkers) return { score: 0, correct: false, partial: points.length > 0 };
  const ordered = [...points].sort((a, b) => a.timeSec - b.timeSec);
  const intervals = ordered.slice(1).map((point, index) => (point.timeSec - ordered[index].timeSec) * 1000);
  if (!intervals.length) return { score: 0, correct: false, partial: false };
  const mean = intervals.reduce((sum, value) => sum + value, 0) / intervals.length;
  const spread = Math.max(...intervals) - Math.min(...intervals);
  const regular = spread <= interaction.toleranceMs;
  const progressive = intervals.every((value, index) => index === 0 || value >= intervals[index - 1] - interaction.toleranceMs / 3);
  const variable = spread > interaction.toleranceMs;
  const correct =
    interaction.expectedPattern === "regular" ? regular
      : interaction.expectedPattern === "progressive" ? progressive && variable
        : interaction.expectedPattern === "variable" ? variable
          : variable && mean > 0;
  return { score: correct ? 1 : 0.35, correct, partial: !correct };
}

function branchFor(feedback: FeedbackBranch[], state: FeedbackBranch["when"]) {
  return feedback.find((branch) => branch.when === state)
    ?? feedback.find((branch) => branch.when === (state === "not_assessable" ? "incorrect" : state))
    ?? feedback.find((branch) => branch.when === (state === "partially_correct" ? "incorrect" : state))
    ?? feedback[0];
}

export function gradeInteraction(
  interaction: LearningInteraction,
  response: unknown,
  attempts: number,
  context: GradeContext = {},
): InteractionEvidence {
  let score = 0;
  let correct = false;
  let partial = false;
  let misconceptions: string[] = [];
  let measuredValueMs: number | undefined;
  let selectedPoints: ECGPoint[] | undefined;
  let notAssessable = false;

  if (interaction.kind === "single_select") {
    correct = response === interaction.correctOptionId;
    score = correct ? 1 : 0;
  } else if (interaction.kind === "multi_select") {
    const selected = new Set(Array.isArray(response) ? response.map(String) : []);
    const expected = new Set(interaction.correctOptionIds);
    const hits = [...expected].filter((id) => selected.has(id)).length;
    const extras = [...selected].filter((id) => !expected.has(id)).length;
    score = expected.size ? hits / expected.size : 0;
    if (interaction.rejectExtraSelections && extras) score = Math.max(0, score - extras / Math.max(1, interaction.options.length));
    correct = hits >= (interaction.minimumCorrect ?? expected.size) && (!interaction.rejectExtraSelections || extras === 0);
    partial = !correct && hits > 0;
  } else if (interaction.kind === "sequence") {
    const order = Array.isArray(response) ? response.map(String) : [];
    const positions = interaction.correctOrder.filter((id, index) => order[index] === id).length;
    score = positions / interaction.correctOrder.length;
    correct = score === 1;
    partial = !correct && score > 0;
  } else if (interaction.kind === "lead_select") {
    const selected = Array.isArray(response) ? response.map(String) : [];
    const expected = interaction.correctLeads;
    if (interaction.selectionMode === "ordered") {
      const matches = expected.filter((lead, index) => selected[index] === lead).length;
      score = matches / expected.length;
      correct = score === 1 && (!interaction.rejectExtraSelections || selected.length === expected.length);
    } else {
      const selectedSet = new Set(selected);
      const hits = expected.filter((lead) => selectedSet.has(lead)).length;
      const extras = selected.filter((lead) => !expected.includes(lead)).length;
      score = hits / expected.length;
      if (interaction.rejectExtraSelections && extras) score = Math.max(0, score - extras / 12);
      correct = hits === expected.length && (!interaction.rejectExtraSelections || extras === 0);
    }
    partial = !correct && score > 0;
  } else if (interaction.kind === "vector_lab") {
    const structured = response && typeof response === "object" ? response as { angleDeg?: unknown; predictions?: Record<string, string> } : null;
    const angle = typeof response === "number" ? response : Number(structured?.angleDeg);
    const difference = Number.isFinite(angle) ? circularDifference(angle, interaction.targetAngleDeg) : 180;
    const angleScore = Math.max(0, 1 - difference / Math.max(interaction.toleranceDeg * 3, 1));
    const predictions = structured?.predictions ?? {};
    const predictionHits = (interaction.predictions ?? []).filter((prediction) => predictions[prediction.lead] === prediction.expected).length;
    const predictionScore = interaction.predictions?.length ? predictionHits / interaction.predictions.length : 1;
    score = interaction.predictions?.length ? angleScore * 0.6 + predictionScore * 0.4 : angleScore;
    correct = difference <= interaction.toleranceDeg && predictionScore === 1;
    partial = !correct && (angleScore > 0 || predictionHits > 0);
  } else if (interaction.kind === "point" || interaction.kind === "region") {
    const result = response as { correct?: boolean; noTarget?: boolean; point?: ECGPoint; points?: ECGPoint[] } | null;
    notAssessable = Boolean(result?.noTarget);
    correct = notAssessable || Boolean(result?.correct);
    score = correct ? 1 : 0;
    selectedPoints = result?.points ?? (result?.point ? [result.point] : undefined);
  } else if (interaction.kind === "caliper") {
    const structured = response && typeof response === "object" ? response as { valueMs?: unknown; correct?: boolean; noTarget?: boolean } : null;
    const value = typeof response === "number" ? response : Number(structured?.valueMs);
    measuredValueMs = Number.isFinite(value) ? value : undefined;
    const expected = numericMeasurement(interaction, context);
    notAssessable = Boolean(structured?.noTarget);
    if (notAssessable) {
      correct = true;
      score = 1;
    } else if (expected === null || measuredValueMs === undefined) {
      correct = false;
      score = 0;
    } else {
      const difference = Math.abs(measuredValueMs - expected);
      const boundaryCorrect = structured?.correct !== false;
      correct = boundaryCorrect && difference <= interaction.target.toleranceMs;
      score = Math.max(0, 1 - difference / Math.max(interaction.target.toleranceMs * 3, 1));
      if (!boundaryCorrect) score = Math.min(score, 0.35);
      partial = !correct && score > 0;
    }
  } else if (interaction.kind === "march") {
    selectedPoints = Array.isArray(response) ? response as ECGPoint[] : [];
    ({ score, correct, partial } = gradeMarch(interaction, selectedPoints));
  } else if (interaction.kind === "compare") {
    const answers = response && typeof response === "object" ? response as Record<string, { left?: string; right?: string }> : {};
    const fieldScores = interaction.dimensions.flatMap((dimension) => {
      const answer = answers[dimension.id];
      return [semanticFieldScore(answer?.left ?? "", dimension.leftAnswer), semanticFieldScore(answer?.right ?? "", dimension.rightAnswer)];
    });
    score = fieldScores.length ? fieldScores.reduce((sum, value) => sum + value, 0) / fieldScores.length : 0;
    correct = fieldScores.length > 0 && fieldScores.every((value) => value >= 0.6) && score >= 0.72;
    partial = !correct && score > 0;
  } else if (interaction.kind === "free_response") {
    const text = normalize(String(response ?? ""));
    const criteria = interaction.rubric.map((criterion) => ({
      ...criterion,
      met: criterion.acceptedConcepts.some((concept) => text.includes(normalize(concept)) || semanticFieldScore(text, concept) >= 0.7),
    }));
    const required = criteria.filter((criterion) => criterion.required);
    const requiredMet = required.filter((criterion) => criterion.met).length;
    const optionalMet = criteria.filter((criterion) => !criterion.required && criterion.met).length;
    score = required.length ? (requiredMet + optionalMet * 0.35) / (required.length + criteria.filter((c) => !c.required).length * 0.35) : 0;
    correct = requiredMet === required.length && String(response ?? "").trim().length >= interaction.minimumCharacters;
    partial = !correct && requiredMet > 0;
    misconceptions = criteria.filter((criterion) => criterion.required && !criterion.met && criterion.misconceptionIfMissing).map((criterion) => criterion.misconceptionIfMissing as string);
  } else if (interaction.kind === "clinical_stage") {
    const answers = response && typeof response === "object" ? response as Record<string, string> : {};
    const unsafe = interaction.stages.some((stage) => stage.unsafeOptionIds?.includes(answers[stage.id]));
    const hits = interaction.stages.filter((stage) => stage.acceptableOptionIds.includes(answers[stage.id])).length;
    score = unsafe ? 0 : hits / interaction.stages.length;
    correct = !unsafe && hits === interaction.stages.length;
    partial = !correct && !unsafe && hits > 0;
    if (unsafe) misconceptions = ["unsafe_clinical_priority"];
  } else if (interaction.kind === "hotspot_map") {
    const selected = Array.isArray(response) ? response.map(String) : [];
    const expected = interaction.correctHotspotIds;
    if (interaction.selectionMode === "ordered") {
      const hits = expected.filter((id, index) => selected[index] === id).length;
      score = hits / expected.length;
      correct = hits === expected.length && selected.length === expected.length;
    } else {
      const selectedSet = new Set(selected);
      const hits = expected.filter((id) => selectedSet.has(id)).length;
      const extras = selected.filter((id) => !expected.includes(id)).length;
      score = Math.max(0, hits / expected.length - extras / Math.max(1, interaction.hotspots.length));
      correct = hits === expected.length && extras === 0;
    }
    partial = !correct && score > 0;
  } else if (interaction.kind === "model_explore") {
    const visited = new Set(Array.isArray(response) ? response.map(String) : []);
    const hits = interaction.requiredFrameIds.filter((id) => visited.has(id)).length;
    score = hits / interaction.requiredFrameIds.length;
    correct = hits === interaction.requiredFrameIds.length;
    partial = !correct && hits > 0;
  } else if (interaction.kind === "numeric_entry") {
    const value = typeof response === "number" ? response : Number(response);
    const expected = numericMeasurement(interaction, context);
    if (Number.isFinite(value) && expected !== null) {
      const difference = Math.abs(value - expected);
      correct = difference <= interaction.target.tolerance;
      score = Math.max(0, 1 - difference / Math.max(interaction.target.tolerance * 3, 1));
      partial = !correct && score > 0;
    }
  } else if (interaction.kind === "pairing") {
    const pairs = response && typeof response === "object" ? response as Record<string, string> : {};
    const entries = Object.entries(interaction.correctPairs);
    const hits = entries.filter(([left, right]) => pairs[left] === right).length;
    score = entries.length ? hits / entries.length : 0;
    correct = hits === entries.length;
    partial = !correct && hits > 0;
  } else if (interaction.kind === "categorize") {
    const categories = response && typeof response === "object" ? response as Record<string, string> : {};
    const entries = Object.entries(interaction.correctCategoryByItem);
    const hits = entries.filter(([item, category]) => categories[item] === category).length;
    score = entries.length ? hits / entries.length : 0;
    correct = hits === entries.length;
    partial = !correct && hits > 0;
  }

  const feedbackBranch: FeedbackBranch["when"] = notAssessable ? "not_assessable" : correct ? "correct" : partial ? "partially_correct" : "incorrect";
  // Resolve the branch here so malformed scene content is caught during use as
  // well as by the static curriculum validator.
  branchFor(interaction.feedback, feedbackBranch);
  return {
    interactionId: interaction.id,
    kind: interaction.kind,
    correct,
    partial,
    score: Number(Math.max(0, Math.min(1, score)).toFixed(3)),
    attempts,
    assistance: notAssessable || attempts > interaction.maxAttemptsBeforeScaffold ? "scaffolded" : "independent",
    hintsUsed: attempts > interaction.maxAttemptsBeforeScaffold ? 1 : 0,
    response,
    selectedPoints,
    measuredValueMs,
    misconceptions,
    feedbackBranch,
  };
}

export function feedbackFor(interaction: LearningInteraction, evidence: InteractionEvidence) {
  return branchFor(interaction.feedback, evidence.feedbackBranch);
}
