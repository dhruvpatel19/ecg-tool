import type { ExternalModuleCoverageDescriptor } from "@/lib/learning/validateCurriculum";

/**
 * Foundations is a mature, same-origin hosted experience. It participates in
 * curriculum order and source-coverage validation, but it is deliberately not
 * represented as a ProductionModule because it does not execute native scenes.
 */
export const FOUNDATIONS_EXTERNAL_MODULE: ExternalModuleCoverageDescriptor = {
  kind: "external_host",
  id: "foundations",
  order: 1,
  title: "Foundations — Reading an ECG",
  shortTitle: "Foundations",
  route: "/learn/foundations",
  duration: "About 25 minutes · 13 resumable scenes",
  outcome: "Orient to the calibrated 12-lead page; identify waves and interval boundaries; measure rate, PR, and QRS; and complete a systematic descriptive read before assigning pathology.",
  prerequisiteIds: [],
  sourceRequirementIds: ["SPEC-11.1", "SPEC-11.3", "SPEC-11.5"],
  sources: [
    {
      document: "docs/storyboards/VERBATIM_M01_M03.md",
      section: "M01.S0–M01.S12 and the M01 source/assessment coverage matrix",
      requirementIds: ["SPEC-11.1", "SPEC-11.3", "SPEC-11.5"],
    },
    {
      document: "docs/storyboard-foundations.md",
      section: "Implemented 13-scene Foundations storyboard",
      requirementIds: ["SPEC-11.1", "SPEC-11.3", "SPEC-11.5"],
    },
    {
      document: "ECG_PLATFORM_SPEC.md",
      section: "§11.1, §11.3, and §11.5",
      requirementIds: ["SPEC-11.1", "SPEC-11.3", "SPEC-11.5"],
    },
  ],
  coveredSubtopicsByRequirement: {
    "SPEC-11.1": ["paper speed", "calibration", "amplitude", "time", "12-lead layout"],
    "SPEC-11.3": ["regular method", "irregular method", "calibration"],
    "SPEC-11.5": ["P onset", "QRS onset", "rate/context"],
  },
  implementation: {
    artifact: "frontend/public/foundations/index.html",
    sceneCount: 13,
    progressContract: "foundations_state_v1 localStorage plus same-origin foundations progress postMessage events",
  },
};

export default FOUNDATIONS_EXTERNAL_MODULE;
