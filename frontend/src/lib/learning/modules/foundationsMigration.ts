/**
 * Stable seam for the native Foundations runtime and its one-time migration
 * from the retired aggregate progress record. Scene ids are durable deep-link
 * and learner-record identifiers and must not be renumbered.
 */
export const FOUNDATIONS_RUNTIME_MANIFEST = {
  id: "foundations",
  title: "Foundations of ECG Interpretation",
  route: "/learn/foundations",
  migrationStrategy: "legacy_read_native_write",
  runtime: "native_production",
  sceneIds: Array.from({ length: 13 }, (_, index) => `S${index}`),
  sweep: [
    "Calibration & quality",
    "Regularity & rate",
    "Atrial source & P–QRS",
    "Axis",
    "Timing: PR, QRS, QT span",
    "ST–T",
    "Synthesis",
  ],
  evidencePolicy: {
    nativeRuntimeCeiling: "guided",
    medianCompositeSupportsRhythmTiming: false,
    missingTruthDefaultsToNormal: false,
    legacyFinishedMeansMastered: false,
    independentMasteryEnabled: false,
  },
} as const;

export const FOUNDATIONS_TOTAL_SCENES = FOUNDATIONS_RUNTIME_MANIFEST.sceneIds.length;

export function isFoundationSceneId(value: string | null): value is string {
  return Boolean(value && FOUNDATIONS_RUNTIME_MANIFEST.sceneIds.includes(value));
}
