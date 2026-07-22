export type FoundationsRepresentation =
  | "continuous_3s_lead_ii"
  | "median_morphology_composite"
  | "complete_packet_mixed_representation";

export type FoundationsCaseRole =
  | "modeled"
  | "guided"
  | "immediate_integration"
  | "equivalent_retry"
  | "component_contrast";

export type FoundationsCaseAllocationSummary = {
  role: FoundationsCaseRole;
  count: number;
  representationCounts: Partial<Record<FoundationsRepresentation, number>>;
  evidenceCeiling: "guided" | "contrast_only";
  permittedUses: string[];
  unavailableEvidence: string[];
};

/**
 * Answer-free browser metadata for the governed Foundations release.
 *
 * Corpus identifiers and learner-stable allocation order remain private to the
 * server. The client receives only opaque pool-slot keys on scene contracts and
 * this aggregate summary, so inspecting the JavaScript bundle cannot reveal the
 * examples, retries, or integration cases assigned to a learner.
 */
export const M01_CASE_ALLOCATION_SUMMARY: FoundationsCaseAllocationSummary[] = [
  {
    role: "modeled",
    count: 2,
    representationCounts: { complete_packet_mixed_representation: 2 },
    evidenceCeiling: "guided",
    permittedUses: ["lead_navigation", "morphology_description"],
    unavailableEvidence: ["independent_intervals", "cross_panel_timing"],
  },
  {
    role: "guided",
    count: 3,
    representationCounts: {
      complete_packet_mixed_representation: 2,
      median_morphology_composite: 1,
    },
    evidenceCeiling: "guided",
    permittedUses: ["lead_navigation", "guided_synthesis", "morphology_description", "not_assessable_decision"],
    unavailableEvidence: ["independent_landmarks", "retention"],
  },
  {
    role: "immediate_integration",
    count: 2,
    representationCounts: { complete_packet_mixed_representation: 2 },
    evidenceCeiling: "guided",
    permittedUses: ["guided_integrated_read"],
    unavailableEvidence: ["independent_transfer", "retention"],
  },
  {
    role: "equivalent_retry",
    count: 4,
    representationCounts: {
      continuous_3s_lead_ii: 1,
      complete_packet_mixed_representation: 3,
    },
    evidenceCeiling: "guided",
    permittedUses: ["short_strip_regular_spacing", "guided_p_qrs_observation", "lead_navigation", "guided_description"],
    unavailableEvidence: ["six_second_rate", "independent_rhythm", "independent_geometry"],
  },
  {
    role: "component_contrast",
    count: 13,
    representationCounts: { median_morphology_composite: 13 },
    evidenceCeiling: "contrast_only",
    permittedUses: ["lead_navigation", "morphology_contrast"],
    unavailableEvidence: ["rate", "regularity", "beat_to_beat_rhythm", "independent_landmarks", "cross_panel_timing"],
  },
];

export function validateM01CaseAllocations() {
  const roles = M01_CASE_ALLOCATION_SUMMARY.map((item) => item.role);
  const duplicateRoles = roles.filter((role, index) => roles.indexOf(role) !== index);
  const count = M01_CASE_ALLOCATION_SUMMARY.reduce((total, item) => total + item.count, 0);
  const representationCountsMatch = M01_CASE_ALLOCATION_SUMMARY.every((item) => (
    Object.values(item.representationCounts).reduce<number>((total, value) => total + (value ?? 0), 0) === item.count
  ));
  return {
    valid: duplicateRoles.length === 0
      && roles.length === 5
      && count === 24
      && representationCountsMatch,
    duplicateRoles: Array.from(new Set(duplicateRoles)),
    count,
    roleCount: roles.length,
  };
}
