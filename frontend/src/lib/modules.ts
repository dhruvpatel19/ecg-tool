// Front-end registry of LEARNING MODULES (the "Learn" mode = guided tutorials).
//
// This is the lightweight hub metadata projection used by client-side overview
// surfaces. The executable native-module registry, ordering assertion, and source
// coverage gate live in ./learning/modules/index.ts; keep this projection aligned
// without importing every storyboard into the curriculum hub bundle. It
// intentionally does NOT consume the backend `/curriculum` endpoint.
//
// Forward-compatibility: a module's experience can be an embedded iframe (Foundations
// today) or, later, a native React route. Either way it fills the SAME registry entry
// and re-emits the same progress contract (see ./progress.ts) — so the hub, nav, and
// sequencing are unaffected by how an individual module is implemented.

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
    title: "Foundations — Reading an ECG",
    blurb:
      "The beginner sweep, end to end: the waves and the grid, rate, rhythm/sinus, intervals, axis, and a systematic read — described, not diagnosed.",
    status: "ready",
    href: "/learn/foundations",
    prerequisites: [],
    sceneCount: 13,
    progressKey: "foundations",
  },
  {
    id: "leads-vectors",
    order: 1,
    title: "Leads, Vectors, Axis & the Normal 12-Lead",
    blurb: "Why the same beat looks different in twelve views: projection, territories, full axis, R-wave progression, and lead-placement checks.",
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
    blurb: "A repeatable rhythm ladder for rate, sinus source, premature/escape beats, pauses, patterned ectopy, and artifact.",
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
    blurb: "PR behavior, dropped conduction, honest 2:1 uncertainty, AV dissociation, escape rhythms, and perfusion-aware bradycardia reasoning.",
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
    blurb: "QRS width and morphology, bundle/fascicular mechanisms, pre-excitation, pacing, and secondary ST-T change.",
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
    blurb: "Stability first, then AF/flutter/SVT and a safety-focused, data-gated approach to wide-complex tachycardia.",
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
    blurb: "Atrial morphology, LVH/RVH evidence, normal and poor R-wave progression, strain patterns, body-habitus/placement effects, and false-positive discipline.",
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
    blurb: "ST-T description, manual QT/QTc, rate correction, wide-QRS confounding, and cautious medication/electrolyte safety links.",
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
    blurb: "Contiguous and reciprocal patterns, established infarction, localization, common mimics, serial reasoning, and the acute-data boundary.",
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
    blurb: "Prioritized reads, machine disagreement, communication, clinic/ward/ED transfer, and exact adaptive remediation loops.",
    status: "ready",
    href: "/learn/integration-transfer",
    prerequisites: ["rhythm-ectopy", "av-brady", "ventricular-conduction", "tachyarrhythmias", "chambers-voltage", "repolarization-safety", "ischemia-infarction"],
    sceneCount: 12,
    progressKey: "production",
  },
];

export const MODULE_COUNT = MODULES.length;
