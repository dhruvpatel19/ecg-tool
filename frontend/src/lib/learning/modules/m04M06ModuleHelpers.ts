import type {
  AccessibilityContract,
  CaseContract,
  CrossModeHandoff,
  FeedbackBranch,
  LearningInteraction,
  LearningSubskill,
  ProductionScene,
  SceneLayoutContract,
  SourceReference,
  TutorSceneContract,
  VerbatimSceneCopy,
} from "@/lib/learning/interactionTypes";

const STORYBOARD = "docs/storyboards/VERBATIM_M04_M06.md";

export function sources(sceneId: string, requirementIds: string[]): SourceReference[] {
  return [
    { document: "ECG_PLATFORM_SPEC.md", section: "§§7, 8, 11, 12, and 16", requirementIds },
    { document: STORYBOARD, section: sceneId, requirementIds: [`VERBATIM-${sceneId}`] },
  ];
}

export function responsiveLayout(delta: string, viewerPlacement: SceneLayoutContract["viewerPlacement"] = "inside_task"): SceneLayoutContract {
  return {
    desktop: `72 px header; 216 px module rail; ECG/model stage in columns 3–9; 340–380 px Luna panel in columns 10–12. ${delta}`,
    laptop: `60 px header with a one-line scene strip; seven-column stage and five-column Luna panel; Luna may collapse behind Reopen Luna. ${delta}`,
    mobile: `Scene title, essential copy, ECG/model, interaction, feedback, Ask Luna sheet, then navigation. Use a pannable lead board rather than shrinking ECG boxes. ${delta}`,
    focusOrder: ["scene heading", "learning setup", "ECG or teaching model", "task controls", "feedback", "Luna tutor", "navigation"],
    viewerPlacement,
  };
}

export function sceneCopy(values: {
  eyebrow: string;
  title: string;
  objective: string;
  openingTutorMessage: string;
  setup: string[];
  mechanismNarration: string[];
  clinicalConnectionHeading: string;
  clinicalConnectionBody: string;
  transitionIntoTask: string;
  completionHeading?: string;
  completionBody: string;
  returnLabel?: string;
}): VerbatimSceneCopy {
  return {
    ...values,
    completionHeading: values.completionHeading ?? "Checkpoint complete",
    returnLabel: values.returnLabel ?? "Return to lesson",
  };
}

export function tutorContract(values: {
  socratic: string;
  hints: [string, string];
  tangentBridge: string;
  returnPrompt: string;
}): TutorSceneContract {
  return {
    socraticPrompts: [values.socratic],
    hintLadder: values.hints,
    tangentBridge: values.tangentBridge,
    returnPrompt: values.returnPrompt,
    caseUnavailablePrompt: "This learning case did not pass its evidence check. Your exact place is saved; use the authored teaching model or choose an equivalent eligible case.",
  };
}

export function caseSpec(values: CaseContract): CaseContract {
  return values;
}

export function accessibility(values: {
  instructions: string;
  keyboard: string;
  summary: string;
  reducedMotion?: string;
}): AccessibilityContract {
  return {
    instructions: values.instructions,
    keyboardAlternative: values.keyboard,
    screenReaderSummary: values.summary,
    reducedMotionAlternative: values.reducedMotion ?? "Use numbered static frames with Previous step and Next step; no information depends on motion or color.",
  };
}

export function feedback(values: {
  correct: string;
  partial: string;
  incorrect: string;
  unsafe: string;
  notAssessable: string;
  evidenceCue: string;
}): FeedbackBranch[] {
  return [
    { id: "correct", when: "correct", heading: "Evidence aligned", body: values.correct },
    { id: "partial", when: "partially_correct", heading: "Partly supported", body: values.partial, evidenceCue: values.evidenceCue },
    { id: "incorrect", when: "incorrect", heading: "Not yet", body: values.incorrect, evidenceCue: values.evidenceCue },
    { id: "unsafe", when: "unsafe", heading: "Pause at the tracing", body: values.unsafe, evidenceCue: values.evidenceCue },
    { id: "not-assessable", when: "not_assessable", heading: "Assessability check", body: values.notAssessable, evidenceCue: values.evidenceCue },
  ];
}

export function completion(interactions: LearningInteraction[], minimumScore = 0.8, equivalentRetryOnCriticalMiss = true): ProductionScene["completionRule"] {
  return {
    requiredInteractionIds: interactions.filter((item) => item.requiredForCompletion).map((item) => item.id),
    minimumScore,
    requireIndependentAttempt: true,
    equivalentRetryOnCriticalMiss,
  };
}

export function handoff(
  mode: CrossModeHandoff["mode"],
  label: string,
  concept: string,
  subskill: CrossModeHandoff["subskill"],
  supportLevel: CrossModeHandoff["supportLevel"],
): CrossModeHandoff {
  return { mode, label, concept, subskill, supportLevel };
}

export function buildScene(values: Omit<ProductionScene, "completionRule"> & { minimumScore?: number; retry?: boolean }): ProductionScene {
  const { minimumScore, retry, ...scene } = values;
  return {
    ...scene,
    completionRule: completion(scene.interactions, minimumScore ?? 0.8, retry ?? true),
  };
}

type CompactInteractionBase = {
  id: string;
  prompt: string;
  instructions: string;
  subskills: LearningSubskill[];
  feedback: FeedbackBranch[];
  accessibility: AccessibilityContract;
  requiredForCompletion?: boolean;
  maxAttemptsBeforeScaffold?: number;
};

function base(values: CompactInteractionBase) {
  return {
    ...values,
    requiredForCompletion: values.requiredForCompletion ?? true,
    maxAttemptsBeforeScaffold: values.maxAttemptsBeforeScaffold ?? 2,
  };
}

export function compactInteraction(
  values: CompactInteractionBase & (
    | { kind: "march"; target: "p_waves" | "qrs_complexes" | "rr_intervals"; minimumMarkers: number; expectedPattern: "regular" | "progressive" | "variable" | "dissociated"; toleranceMs: number }
    | { kind: "caliper"; measurement: "rr" | "pr" | "qrs" | "qt" | "custom"; target: Extract<LearningInteraction, { kind: "caliper" }>["target"]; requireBoundaryLabels?: boolean }
    | { kind: "region"; concept: string; allowedLeads?: string[]; minimumDurationMs?: number }
    | { kind: "point"; concept: string; gradePrompt: string; allowedLeads?: string[] }
    | { kind: "vector_lab"; initialAngleDeg: number; targetAngleDeg: number; toleranceDeg: number; targetLabel: string; predictions?: Extract<LearningInteraction, { kind: "vector_lab" }>["predictions"] }
    | { kind: "compare"; leftCaseConcept: string; rightCaseConcept: string; dimensions: Extract<LearningInteraction, { kind: "compare" }>["dimensions"] }
    | { kind: "sequence"; cards: Extract<LearningInteraction, { kind: "sequence" }>["cards"]; correctOrder: string[] }
    | { kind: "single_select"; options: Extract<LearningInteraction, { kind: "single_select" }>["options"]; correctOptionId: string }
    | { kind: "multi_select"; options: Extract<LearningInteraction, { kind: "multi_select" }>["options"]; correctOptionIds: string[]; minimumCorrect?: number; rejectExtraSelections?: boolean }
    | { kind: "free_response"; responseLabel: string; placeholder: string; minimumCharacters: number; rubric: Extract<LearningInteraction, { kind: "free_response" }>["rubric"]; sentenceFrame?: string }
    | { kind: "clinical_stage"; stages: Extract<LearningInteraction, { kind: "clinical_stage" }>["stages"] }
    | { kind: "lead_select"; selectionMode: "single" | "multiple" | "ordered"; correctLeads: string[]; allowedLeads?: string[]; rejectExtraSelections?: boolean }
    | { kind: "hotspot_map"; canvas: "torso" | "hexaxial" | "conduction_tree" | "waveform" | "heart"; selectionMode: "single" | "multiple" | "ordered"; hotspots: Extract<LearningInteraction, { kind: "hotspot_map" }>["hotspots"]; correctHotspotIds: string[] }
    | { kind: "model_explore"; model: "cardiac_cycle" | "vector_projection" | "av_ladder" | "bundle_activation" | "reentry" | "repolarization"; frames: Extract<LearningInteraction, { kind: "model_explore" }>["frames"]; requiredFrameIds: string[] }
    | { kind: "numeric_entry"; label: string; unit: "bpm" | "ms" | "mV" | "degrees" | "boxes" | "ratio"; target: Extract<LearningInteraction, { kind: "numeric_entry" }>["target"]; minimum?: number; maximum?: number }
    | { kind: "pairing"; left: Extract<LearningInteraction, { kind: "pairing" }>["left"]; right: Extract<LearningInteraction, { kind: "pairing" }>["right"]; correctPairs: Record<string, string> }
    | { kind: "categorize"; items: Extract<LearningInteraction, { kind: "categorize" }>["items"]; categories: Extract<LearningInteraction, { kind: "categorize" }>["categories"]; correctCategoryByItem: Record<string, string> }
  ),
): LearningInteraction {
  return { ...base(values), ...values } as LearningInteraction;
}
