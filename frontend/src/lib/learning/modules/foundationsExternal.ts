import type { ExternalModuleCoverageDescriptor } from "@/lib/learning/validateCurriculum";
import { FOUNDATIONS_RUNTIME_MANIFEST } from "@/lib/learning/modules/foundationsMigration";

/**
 * @deprecated Historical audit compatibility only. Foundations now runs as
 * M01_FOUNDATIONS_MODULE in the native production registry. Do not import this
 * descriptor into the learner runtime or use it to restore the retired public
 * prototype.
 */
export const FOUNDATIONS_EXTERNAL_MODULE: ExternalModuleCoverageDescriptor = {
  kind: "external_host",
  id: FOUNDATIONS_RUNTIME_MANIFEST.id,
  order: 1,
  title: FOUNDATIONS_RUNTIME_MANIFEST.title,
  shortTitle: "Foundations",
  route: FOUNDATIONS_RUNTIME_MANIFEST.route,
  duration: "About 1½–2 hours · four resumable chapters · 13 scenes",
  outcome: "Check calibration and task-specific quality; identify waveform landmarks; estimate ventricular rate; describe the visible P–QRS relationship; classify coarse axis; measure PR and QRS; and communicate an evidence-linked descriptive read.",
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
    artifact: "frontend/src/lib/learning/modules/m01Foundations.ts",
    sceneCount: FOUNDATIONS_RUNTIME_MANIFEST.sceneIds.length,
    progressContract: "server-owned production-curriculum scene rows, durable guided-evidence outbox, native deep links, and legacy-read/native-write migration",
  },
};

export default FOUNDATIONS_EXTERNAL_MODULE;
