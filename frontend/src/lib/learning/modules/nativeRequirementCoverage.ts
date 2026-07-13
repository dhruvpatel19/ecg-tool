import type { NativeRequirementCoverageDescriptor } from "@/lib/learning/validateCurriculum";

/**
 * Mechanical audit trail from every binding ECG_PLATFORM_SPEC.md §11 subtopic
 * taught in a native module to the exact production scene that teaches it.
 * Foundations is mapped separately by its external-host coverage descriptor.
 */
export const NATIVE_REQUIREMENT_COVERAGE: NativeRequirementCoverageDescriptor[] = [
  {
    requirementId: "SPEC-11.2",
    moduleId: "leads-vectors",
    scenes: [
      { sceneId: "M02.S5", coveredSubtopics: ["limb leads"] },
      { sceneId: "M02.S7", coveredSubtopics: ["precordial leads"] },
      { sceneId: "M02.S9", coveredSubtopics: ["territories", "contiguous leads"] },
    ],
  },
  {
    requirementId: "SPEC-11.4",
    moduleId: "rhythm-ectopy",
    scenes: [
      { sceneId: "M03.S0", coveredSubtopics: ["P waves"] },
      { sceneId: "M03.S2", coveredSubtopics: ["regularity"] },
      { sceneId: "M03.S4", coveredSubtopics: ["sinus rhythm"] },
    ],
  },
  {
    requirementId: "SPEC-11.6",
    moduleId: "leads-vectors",
    scenes: [
      { sceneId: "M02.S6", coveredSubtopics: ["hexaxial method"] },
      { sceneId: "M02.S10", coveredSubtopics: ["I/aVF"] },
      { sceneId: "M02.S11", coveredSubtopics: ["lead II refinement"] },
    ],
  },
  {
    requirementId: "SPEC-11.7",
    moduleId: "ventricular-conduction",
    scenes: [
      { sceneId: "m05-s0", coveredSubtopics: ["QRS boundaries", "duration", "morphology distinction"] },
    ],
  },
  {
    requirementId: "SPEC-11.8",
    moduleId: "ventricular-conduction",
    scenes: [
      { sceneId: "m05-s0", coveredSubtopics: ["width plus morphology"] },
      { sceneId: "m05-s2", coveredSubtopics: ["RBBB"] },
      { sceneId: "m05-s3", coveredSubtopics: ["LBBB"] },
    ],
  },
  {
    requirementId: "SPEC-11.9",
    moduleId: "chambers-voltage",
    scenes: [
      { sceneId: "m07-s4", coveredSubtopics: ["V1–V6 sequence", "transition"] },
      { sceneId: "m07-s5", coveredSubtopics: ["poor-progression differential"] },
    ],
  },
  {
    requirementId: "SPEC-11.10",
    moduleId: "chambers-voltage",
    scenes: [
      { sceneId: "m07-s1", coveredSubtopics: ["atrial enlargement"] },
      { sceneId: "m07-s2", coveredSubtopics: ["LVH", "criteria limits"] },
      { sceneId: "m07-s3", coveredSubtopics: ["RVH"] },
    ],
  },
  {
    requirementId: "SPEC-11.11",
    moduleId: "repolarization-safety",
    scenes: [
      { sceneId: "m08-s0", coveredSubtopics: ["J point"] },
      { sceneId: "m08-s2", coveredSubtopics: ["ST elevation", "ST depression", "T-wave change"] },
      { sceneId: "m08-s8", coveredSubtopics: ["nonspecific change"] },
    ],
  },
  {
    requirementId: "SPEC-11.12",
    moduleId: "ischemia-infarction",
    scenes: [
      { sceneId: "m09-s1", coveredSubtopics: ["reciprocal evidence"] },
      { sceneId: "m09-s2", coveredSubtopics: ["anterior", "septal", "lateral"] },
      { sceneId: "m09-s3", coveredSubtopics: ["inferior"] },
      { sceneId: "m09-s4", coveredSubtopics: ["posterior"] },
    ],
  },
  {
    requirementId: "SPEC-11.13",
    moduleId: "av-brady",
    scenes: [
      { sceneId: "m04-s3", coveredSubtopics: ["first degree"] },
      { sceneId: "m04-s4", coveredSubtopics: ["Mobitz I"] },
      { sceneId: "m04-s5", coveredSubtopics: ["Mobitz II"] },
      { sceneId: "m04-s6", coveredSubtopics: ["2:1 uncertainty"] },
      { sceneId: "m04-s7", coveredSubtopics: ["complete block"] },
      { sceneId: "m04-s8", coveredSubtopics: ["escape"] },
    ],
  },
  {
    requirementId: "SPEC-11.14",
    moduleId: "tachyarrhythmias",
    scenes: [
      { sceneId: "m06-s2", coveredSubtopics: ["SVT"] },
      { sceneId: "m06-s4", coveredSubtopics: ["flutter"] },
      { sceneId: "m06-s5", coveredSubtopics: ["AF"] },
      { sceneId: "m06-s7", coveredSubtopics: ["wide-complex tachycardia"] },
      { sceneId: "m06-s9", coveredSubtopics: ["reliability gate"] },
    ],
  },
  {
    requirementId: "SPEC-11.15",
    moduleId: "repolarization-safety",
    scenes: [
      { sceneId: "m08-s0", coveredSubtopics: ["QT boundaries"] },
      { sceneId: "m08-s4", coveredSubtopics: ["QTc", "rate correction"] },
      { sceneId: "m08-s6", coveredSubtopics: ["drug workflow"] },
      { sceneId: "m08-s7", coveredSubtopics: ["electrolyte uncertainty"] },
    ],
  },
  {
    requirementId: "SPEC-11.16",
    moduleId: "integration-transfer",
    scenes: [
      { sceneId: "m10-s0", coveredSubtopics: ["standard framework", "HEARTS"] },
      { sceneId: "m10-s2", coveredSubtopics: ["synthesis", "confidence"] },
      { sceneId: "m10-s8", coveredSubtopics: ["communication"] },
    ],
  },
];
