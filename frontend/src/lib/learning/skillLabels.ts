/**
 * Canonical learner-facing competency labels.
 *
 * Skill identifiers remain stable storage and routing keys. Bloom demand and
 * question format belong to task metadata, not this mastery vocabulary.
 */
export const COMPETENCY_TAXONOMY_VERSION = "2026.07.17" as const;

export const COMPETENCY_SKILL_LABELS = {
  recognize: "Recognize and name",
  localize: "Locate the evidence",
  measure: "Measure accurately",
  discriminate: "Distinguish alternatives",
  explain_mechanism: "Explain the mechanism",
  synthesize: "Complete an interpretation",
  compare_change: "Compare and describe change",
  apply_in_context: "Apply in clinical context",
  calibrate_confidence: "Calibrate certainty",
} as const;

export type CompetencySkillId = keyof typeof COMPETENCY_SKILL_LABELS;

const labels: Readonly<Record<string, string>> = COMPETENCY_SKILL_LABELS;

export function competencySkillLabel(
  value: string | null | undefined,
  unavailableLabel = "Skill details unavailable",
) {
  if (!value) return unavailableLabel;
  return labels[value] ?? value.replaceAll("_", " ");
}
