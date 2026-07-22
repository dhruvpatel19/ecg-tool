import { UNSUCCESSFUL_ATTEMPTS_BEFORE_SOLUTION } from "@/lib/learning/interactionTypes";
import type {
  CaliperInteraction,
  FeedbackBranch,
  ForbiddenFreeResponseClaim,
  InteractionEvidence,
  LearningInteraction,
  MarchInteraction,
  NumericEntryInteraction,
} from "@/lib/learning/interactionTypes";
import type { ECGPoint } from "@/lib/coordinates";

type GradeContext = {
  packetMeasurements?: Record<string, unknown>;
  serverMeasurementGrade?: {
    correct: boolean;
    noTarget: boolean;
  };
};

const normalize = (value: string) => value
  .toLowerCase()
  .replace(/[’']/g, "'")
  .replace(/\bcan['’]?t\b/g, "cannot")
  .replace(/\bwon['’]?t\b/g, "will not")
  .replace(/\bdoesn['’]?t\b/g, "does not")
  .replace(/\bdon['’]?t\b/g, "do not")
  .replace(/[^a-z0-9]+/g, " ")
  .trim();

function explicitlyBoundsForbiddenOccurrence(
  normalized: string,
  cursor: number,
  needle: string,
  claimId: string,
) {
  const preceding = normalized.slice(Math.max(0, cursor - 120), cursor).trim();
  const following = normalized.slice(cursor + needle.length, cursor + needle.length + 90).trim();
  if (claimId === "diagnosis") {
    return /\b(?:cannot|unable to|not able to)\s+(?:diagnose|establish|confirm|infer|conclude|assign|call|support)\s*$/.test(preceding)
      || /\b(?:insufficient|inadequate|not enough)\s+(?:evidence|information|context)(?:\s+[a-z0-9]+){0,3}\s+to\s+(?:diagnose|establish|confirm|support)\s*$/.test(preceding)
      || /\bnot\s+diagnostic\s+of\s*$/.test(preceding)
      || (needle === "diagnosis" && /\bno\s*$/.test(preceding))
      || /^(?:cannot|can not)\s+be\s+(?:diagnosed|established|confirmed|determined|supported)\b/.test(following);
  }
  if (claimId === "treatment") {
    return /\b(?:cannot|unable to|not able to)\s+(?:recommend|determine|select|prescribe)\s*$/.test(preceding)
      || /\b(?:cannot|unable to|not able to)\s+(?:diagnose|establish|confirm)(?:\s+[a-z0-9]+){1,4}\s+or\s+(?:recommend|determine)\s*$/.test(preceding)
      || (/\bno\s*$/.test(preceding) && /^(?:recommendation|recommendations)\b/.test(following))
      || /^(?:cannot|can not)\s+be\s+(?:recommended|determined|selected|prescribed)\b/.test(following);
  }
  if (claimId === "urgency") {
    return /\b(?:cannot|unable to|not able to)\s+(?:determine|assign|infer|establish)\s*$/.test(preceding)
      || /^(?:cannot|can not)\s+be\s+(?:determined|assigned|inferred|established)\b/.test(following)
      || (/\bno\s*$/.test(preceding) && /^(?:claim|conclusion|determination)\b/.test(following));
  }
  return false;
}

function assertsForbiddenClaim(text: string, claim: ForbiddenFreeResponseClaim) {
  const normalized = normalize(text);
  return claim.terms.some((term) => {
    const needle = normalize(term);
    if (!needle) return false;
    let cursor = normalized.indexOf(needle);
    while (cursor >= 0) {
      // Only explicit epistemic boundaries exempt a term. Generic negation is
      // unsafe here: "no doubt this is STEMI" and "not only ischemia" are
      // positive assertions, while "can't diagnose ischemia" is a valid limit.
      if (!explicitlyBoundsForbiddenOccurrence(normalized, cursor, needle, claim.id)) return true;
      cursor = normalized.indexOf(needle, cursor + needle.length);
    }
    return false;
  });
}

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
    correct = !notAssessable && Boolean(result?.correct);
    score = correct ? 1 : 0;
    selectedPoints = result?.points ?? (result?.point ? [result.point] : undefined);
  } else if (interaction.kind === "caliper") {
    const structured = response && typeof response === "object" ? response as { valueMs?: unknown; correct?: boolean; noTarget?: boolean } : null;
    const value = typeof response === "number" ? response : Number(structured?.valueMs);
    measuredValueMs = Number.isFinite(value) ? value : undefined;
    const expected = numericMeasurement(interaction, context);
    notAssessable = Boolean(structured?.noTarget);
    if (notAssessable) {
      correct = false;
      score = 0;
    } else if (expected === null && structured?.correct !== undefined) {
      // Guided keeps packet measurements server-side. The region endpoint has
      // already committed and graded these exact boundaries, so its bounded
      // result is authoritative without exposing the target value.
      correct = Boolean(structured.correct);
      score = correct ? 1 : 0;
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
    const answers = response && typeof response === "object" ? response as Record<string, { left?: string; right?: string; third?: string }> : {};
    const fieldScores = interaction.dimensions.flatMap((dimension) => {
      const answer = answers[dimension.id];
      return [
        semanticFieldScore(answer?.left ?? "", dimension.leftAnswer),
        semanticFieldScore(answer?.right ?? "", dimension.rightAnswer),
        ...(interaction.thirdCaseConcept && dimension.thirdAnswer
          ? [semanticFieldScore(answer?.third ?? "", dimension.thirdAnswer)]
          : []),
      ];
    });
    score = fieldScores.length ? fieldScores.reduce((sum, value) => sum + value, 0) / fieldScores.length : 0;
    correct = fieldScores.length > 0 && fieldScores.every((value) => value >= 0.6) && score >= 0.72;
    partial = !correct && score > 0;
  } else if (interaction.kind === "free_response") {
    const rawText = String(response ?? "");
    const text = normalize(rawText);
    const criteria = interaction.rubric.map((criterion) => ({
      ...criterion,
      met: criterion.acceptedConcepts.some((concept) => text.includes(normalize(concept)) || semanticFieldScore(text, concept) >= 0.7),
    }));
    const required = criteria.filter((criterion) => criterion.required);
    const requiredMet = required.filter((criterion) => criterion.met).length;
    const optionalMet = criteria.filter((criterion) => !criterion.required && criterion.met).length;
    score = required.length ? (requiredMet + optionalMet * 0.35) / (required.length + criteria.filter((c) => !c.required).length * 0.35) : 0;
    const forbidden = (interaction.forbiddenClaims ?? []).filter((claim) => assertsForbiddenClaim(rawText, claim));
    correct = requiredMet === required.length && rawText.trim().length >= interaction.minimumCharacters && forbidden.length === 0;
    partial = !correct && requiredMet > 0;
    misconceptions = criteria.filter((criterion) => criterion.required && !criterion.met && criterion.misconceptionIfMissing).map((criterion) => criterion.misconceptionIfMissing as string);
    if (forbidden.length) {
      score = Math.min(score, 0.5);
      misconceptions.push(...forbidden.map((claim) => claim.misconception));
    }
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
    if (context.serverMeasurementGrade) {
      notAssessable = context.serverMeasurementGrade.noTarget;
      correct = !notAssessable && context.serverMeasurementGrade.correct;
      score = correct ? 1 : 0;
    } else if (Number.isFinite(value) && expected !== null) {
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
  } else if (interaction.kind === "waveform_lab") {
    const requiredTargets = interaction.requiredTargetIds
      .map((id) => interaction.targets.find((target) => target.id === id))
      .filter((target): target is NonNullable<typeof target> => Boolean(target));
    if (interaction.task === "point_targets") {
      const points = response && typeof response === "object"
        ? response as Record<string, number>
        : {};
      const hits = requiredTargets.filter((target) => (
        target.timeMs !== undefined
        && Number.isFinite(Number(points[target.id]))
        && Math.abs(Number(points[target.id]) - target.timeMs) <= interaction.toleranceMs
      )).length;
      score = requiredTargets.length ? hits / requiredTargets.length : 0;
      correct = requiredTargets.length > 0 && hits === requiredTargets.length;
      partial = !correct && hits > 0;
    } else if (interaction.task === "interval" || interaction.task === "region") {
      const selection = response && typeof response === "object"
        ? response as { startMs?: number; endMs?: number }
        : {};
      const target = requiredTargets[0];
      const start = Number(selection.startMs);
      const end = Number(selection.endMs);
      if (target?.startMs !== undefined && target.endMs !== undefined && Number.isFinite(start) && Number.isFinite(end)) {
        const orderedStart = Math.min(start, end);
        const orderedEnd = Math.max(start, end);
        const startDifference = Math.abs(orderedStart - target.startMs);
        const endDifference = Math.abs(orderedEnd - target.endMs);
        const boundaryHits = Number(startDifference <= interaction.toleranceMs) + Number(endDifference <= interaction.toleranceMs);
        score = boundaryHits / 2;
        correct = boundaryHits === 2;
        partial = !correct && boundaryHits > 0;
        measuredValueMs = Math.round(orderedEnd - orderedStart);
      }
    } else {
      const markers = Array.isArray(response)
        ? response.map(Number).filter((value) => Number.isFinite(value)).sort((a, b) => a - b)
        : [];
      const expected = requiredTargets
        .map((target) => target.timeMs)
        .filter((value): value is number => value !== undefined)
        .sort((a, b) => a - b);
      const used = new Set<number>();
      const matchedIndices: number[] = [];
      let hits = 0;
      for (const marker of markers) {
        let nearestIndex = -1;
        let nearestDifference = Number.POSITIVE_INFINITY;
        expected.forEach((target, index) => {
          const difference = Math.abs(marker - target);
          if (!used.has(index) && difference < nearestDifference) {
            nearestIndex = index;
            nearestDifference = difference;
          }
        });
        if (nearestIndex >= 0 && nearestDifference <= interaction.toleranceMs) {
          used.add(nearestIndex);
          matchedIndices.push(nearestIndex);
          hits += 1;
        }
      }
      const minimum = interaction.minimumMarkers ?? expected.length;
      const extraMarkers = Math.max(0, markers.length - hits);
      const orderedMatches = [...matchedIndices].sort((a, b) => a - b);
      const consecutive = orderedMatches.every((index, position) => (
        position === 0 || index === orderedMatches[position - 1] + 1
      ));
      // Pattern truth comes from the authored target sequence after the learner
      // clicks have been matched inside tolerance. Using raw click edges here
      // would reject valid consecutive marks simply because one click was early
      // and the next was late within the accepted window.
      const matchedTargetTimes = orderedMatches.map((index) => expected[index]);
      const intervals = matchedTargetTimes.slice(1).map((marker, index) => marker - matchedTargetTimes[index]);
      const intervalSpread = intervals.length
        ? Math.max(...intervals) - Math.min(...intervals)
        : Number.POSITIVE_INFINITY;
      const patternMatches = interaction.expectedPattern === "regular"
        ? intervalSpread <= interaction.toleranceMs * 2
        : interaction.expectedPattern === "variable"
          ? intervalSpread > interaction.toleranceMs
          : true;
      score = Math.max(0, Math.min(1, hits / Math.max(1, minimum) - extraMarkers * 0.1));
      // A partial regular-strip task must use consecutive beats. Otherwise an
      // alternating subset can look perfectly regular while representing the
      // wrong R–R interval and therefore the wrong rate.
      const sequenceMatches = interaction.expectedPattern !== "regular"
        || expected.length <= minimum
        || consecutive;
      correct = hits >= minimum && extraMarkers === 0 && patternMatches && sequenceMatches;
      if (!patternMatches || !sequenceMatches) score = Math.min(score, 0.7);
      partial = !correct && hits > 0;
    }
  }

  const feedbackBranch: FeedbackBranch["when"] = notAssessable ? "not_assessable" : correct ? "correct" : partial ? "partially_correct" : "incorrect";
  const solutionRevealed = !notAssessable
    && !correct
    && attempts >= UNSUCCESSFUL_ATTEMPTS_BEFORE_SOLUTION;
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
    assistance: notAssessable || solutionRevealed || attempts > interaction.maxAttemptsBeforeScaffold ? "scaffolded" : "independent",
    hintsUsed: solutionRevealed || attempts > interaction.maxAttemptsBeforeScaffold ? 1 : 0,
    response,
    selectedPoints,
    measuredValueMs,
    misconceptions,
    feedbackBranch,
    solutionRevealed,
  };
}

export function feedbackFor(interaction: LearningInteraction, evidence: InteractionEvidence) {
  return branchFor(interaction.feedback, evidence.feedbackBranch);
}
