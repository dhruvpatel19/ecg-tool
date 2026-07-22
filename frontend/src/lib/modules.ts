// Front-end registry of LEARNING MODULES (the "Learn" mode = guided tutorials).
//
// This is the lightweight hub metadata projection used by client-side overview
// surfaces. The executable native-module registry, ordering assertion, and source
// coverage gate live in ./learning/modules/index.ts; keep this projection aligned
// without importing every storyboard into the curriculum hub bundle. It
// intentionally does NOT consume the backend `/curriculum` endpoint.
//
// Every ready module now uses the native scene runtime and the same per-scene
// production pathway contract. The earlier Foundations aggregate remains only
// as an immutable migration source.

export type ModuleStatus = "ready" | "coming-soon";

export interface LearnModule {
  id: string;
  order: number;
  title: string;
  blurb: string;
  status: ModuleStatus;
  /** Route for a ready module (e.g. the iframe host). Absent for coming-soon. */
  href?: string;
  /** Module ids that should be done first (advisory — soft sequencing). */
  prerequisites: string[];
  /** For scene-based modules, the scene count used to show progress. */
  sceneCount?: number;
  /** Which progress source backs this module (see ./progress.ts). */
  progressKey?: "foundations" | "production";
}

// Titles/order/prerequisites mirror backend/app/curriculum.py and the v2 storyboard.
export const MODULES: LearnModule[] = [
  {
    id: "foundations",
    order: 0,
    title: "Foundations of ECG Interpretation",
    blurb:
      "Learn what the ECG trace represents, check calibration and task-specific quality, measure basic timing features, navigate the 12-lead page, and complete an evidence-linked descriptive sweep.",
    status: "ready",
    href: "/learn/foundations",
    prerequisites: [],
    sceneCount: 13,
    progressKey: "production",
  },
  {
    id: "leads-vectors",
    order: 1,
    title: "Leads, Vectors, Axis & the Normal 12-Lead",
    blurb: "Electrodes versus leads, vector projection, contiguous territories, full frontal axis, R-wave progression, and placement/normal-variant checks.",
    status: "ready",
    href: "/learn/leads-vectors",
    prerequisites: ["foundations"],
    sceneCount: 15,
    progressKey: "production",
  },
  {
    id: "rhythm-ectopy",
    order: 2,
    title: "Rate, Sinus Rhythm, Pauses & Ectopy",
    blurb: "A repeatable rhythm ladder: rate, regularity, sinus source, premature atrial/ventricular beats, escape beats, pauses, patterns, and artifact.",
    status: "ready",
    href: "/learn/rhythm-ectopy",
    prerequisites: ["foundations"],
    sceneCount: 16,
    progressKey: "production",
  },
  {
    id: "av-brady",
    order: 3,
    title: "AV Conduction & Bradyarrhythmias",
    blurb: "PR behavior, first- and second-degree patterns, honest 2:1 uncertainty, AV dissociation, escape rhythms, and perfusion-aware bradycardia reasoning.",
    status: "ready",
    href: "/learn/av-brady",
    prerequisites: ["rhythm-ectopy"],
    sceneCount: 11,
    progressKey: "production",
  },
  {
    id: "ventricular-conduction",
    order: 4,
    title: "Ventricular Activation, Conduction, Pre-excitation & Pacing",
    blurb: "QRS duration versus morphology, BBB/fascicular mechanisms, pre-excitation, pacing, and secondary ST-T change.",
    status: "ready",
    href: "/learn/ventricular-conduction",
    prerequisites: ["leads-vectors", "av-brady"],
    sceneCount: 11,
    progressKey: "production",
  },
  {
    id: "tachyarrhythmias",
    order: 5,
    title: "Tachyarrhythmias: Narrow, Wide, Regular & Irregular",
    blurb: "Stability first, then mechanism, regularity, width, atrial activity, AF/flutter/SVT, and data-gated wide-complex safety reasoning.",
    status: "ready",
    href: "/learn/tachyarrhythmias",
    prerequisites: ["rhythm-ectopy", "ventricular-conduction"],
    sceneCount: 12,
    progressKey: "production",
  },
  {
    id: "chambers-voltage",
    order: 6,
    title: "Chambers, Voltage & R-Wave Progression",
    blurb: "Atrial morphology, ventricular voltage and axis, LVH/RVH evidence, normal and poor R-wave progression, strain patterns, and false-positive discipline.",
    status: "ready",
    href: "/learn/chambers-voltage",
    prerequisites: ["leads-vectors", "ventricular-conduction"],
    sceneCount: 8,
    progressKey: "production",
  },
  {
    id: "repolarization-safety",
    order: 7,
    title: "Repolarization, QT, Electrolytes & Drugs",
    blurb: "ST-T description, baseline/J point, manual QT/QTc, rate correction, wide-QRS confounding, and cautious medication/electrolyte safety links.",
    status: "ready",
    href: "/learn/repolarization-safety",
    prerequisites: ["ventricular-conduction"],
    sceneCount: 10,
    progressKey: "production",
  },
  {
    id: "ischemia-infarction",
    order: 8,
    title: "Ischemia, Infarction, Territories & Mimics",
    blurb: "Contiguous and reciprocal patterns, established infarction/localization, common mimics, serial reasoning, and an explicit acute-data boundary.",
    status: "ready",
    href: "/learn/ischemia-infarction",
    prerequisites: ["leads-vectors", "ventricular-conduction", "chambers-voltage", "repolarization-safety"],
    sceneCount: 10,
    progressKey: "production",
  },
  {
    id: "integration-transfer",
    order: 9,
    title: "Integrated Interpretation & Clinical Transfer",
    blurb: "Prioritized complete reads, machine disagreement, communication, medication safety, clinic/ward/ED transfer, and exact remediation loops.",
    status: "ready",
    href: "/learn/integration-transfer",
    prerequisites: ["rhythm-ectopy", "av-brady", "ventricular-conduction", "tachyarrhythmias", "chambers-voltage", "repolarization-safety", "ischemia-infarction"],
    sceneCount: 12,
    progressKey: "production",
  },
];

export const MODULE_COUNT = MODULES.length;
