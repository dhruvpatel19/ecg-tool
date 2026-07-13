export type AuthoritativeRequirement = {
  id: string;
  title: string;
  requiredSubtopics: string[];
  primaryModuleId: string;
  spiralModuleIds: string[];
};

/**
 * Binding content spine from ECG_PLATFORM_SPEC.md §11. The detailed storyboards
 * may add clinically useful material, but none of these requirements may vanish
 * or be satisfied only by a cross-mode link.
 */
export const AUTHORITATIVE_REQUIREMENTS: AuthoritativeRequirement[] = [
  { id: "SPEC-11.1", title: "ECG orientation", requiredSubtopics: ["paper speed", "calibration", "amplitude", "time", "12-lead layout"], primaryModuleId: "foundations", spiralModuleIds: ["integration-transfer"] },
  { id: "SPEC-11.2", title: "Lead anatomy", requiredSubtopics: ["limb leads", "precordial leads", "territories", "contiguous leads"], primaryModuleId: "leads-vectors", spiralModuleIds: ["ischemia-infarction"] },
  { id: "SPEC-11.3", title: "Rate", requiredSubtopics: ["regular method", "irregular method", "calibration"], primaryModuleId: "foundations", spiralModuleIds: ["rhythm-ectopy", "tachyarrhythmias", "integration-transfer"] },
  { id: "SPEC-11.4", title: "Rhythm", requiredSubtopics: ["P waves", "regularity", "sinus rhythm"], primaryModuleId: "rhythm-ectopy", spiralModuleIds: ["av-brady", "tachyarrhythmias"] },
  { id: "SPEC-11.5", title: "PR interval", requiredSubtopics: ["P onset", "QRS onset", "rate/context"], primaryModuleId: "foundations", spiralModuleIds: ["av-brady"] },
  { id: "SPEC-11.6", title: "Axis", requiredSubtopics: ["I/aVF", "lead II refinement", "hexaxial method"], primaryModuleId: "leads-vectors", spiralModuleIds: ["ventricular-conduction", "chambers-voltage"] },
  { id: "SPEC-11.7", title: "QRS duration and conduction delay", requiredSubtopics: ["QRS boundaries", "duration", "morphology distinction"], primaryModuleId: "ventricular-conduction", spiralModuleIds: ["tachyarrhythmias"] },
  { id: "SPEC-11.8", title: "Bundle branch blocks", requiredSubtopics: ["RBBB", "LBBB", "width plus morphology"], primaryModuleId: "ventricular-conduction", spiralModuleIds: ["tachyarrhythmias", "repolarization-safety", "ischemia-infarction"] },
  { id: "SPEC-11.9", title: "R-wave progression", requiredSubtopics: ["V1–V6 sequence", "transition", "poor-progression differential"], primaryModuleId: "chambers-voltage", spiralModuleIds: ["leads-vectors", "ischemia-infarction"] },
  { id: "SPEC-11.10", title: "Chamber enlargement and hypertrophy", requiredSubtopics: ["atrial enlargement", "LVH", "RVH", "criteria limits"], primaryModuleId: "chambers-voltage", spiralModuleIds: ["ischemia-infarction", "integration-transfer"] },
  { id: "SPEC-11.11", title: "ST elevation/depression and T-wave changes", requiredSubtopics: ["J point", "ST elevation", "ST depression", "T-wave change", "nonspecific change"], primaryModuleId: "repolarization-safety", spiralModuleIds: ["ischemia-infarction"] },
  { id: "SPEC-11.12", title: "MI localization", requiredSubtopics: ["anterior", "septal", "lateral", "inferior", "posterior", "reciprocal evidence"], primaryModuleId: "ischemia-infarction", spiralModuleIds: ["integration-transfer"] },
  { id: "SPEC-11.13", title: "Bradyarrhythmias and AV block", requiredSubtopics: ["first degree", "Mobitz I", "Mobitz II", "2:1 uncertainty", "complete block", "escape"], primaryModuleId: "av-brady", spiralModuleIds: ["integration-transfer"] },
  { id: "SPEC-11.14", title: "Tachyarrhythmias", requiredSubtopics: ["AF", "flutter", "SVT", "wide-complex tachycardia", "reliability gate"], primaryModuleId: "tachyarrhythmias", spiralModuleIds: ["integration-transfer"] },
  { id: "SPEC-11.15", title: "QT/QTc and electrolyte/drug patterns", requiredSubtopics: ["QT boundaries", "QTc", "rate correction", "drug workflow", "electrolyte uncertainty"], primaryModuleId: "repolarization-safety", spiralModuleIds: ["integration-transfer"] },
  { id: "SPEC-11.16", title: "Integrated clerkship-style interpretation", requiredSubtopics: ["standard framework", "HEARTS", "synthesis", "confidence", "communication"], primaryModuleId: "integration-transfer", spiralModuleIds: [] },
];
