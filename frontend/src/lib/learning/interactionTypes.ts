import type { ECGPoint } from "@/lib/coordinates";

export type LearningSubskill =
  | "recognize"
  | "localize"
  | "measure"
  | "discriminate"
  | "explain_mechanism"
  | "synthesize"
  | "apply_in_context"
  | "calibrate_confidence";

export type InteractionKind =
  | "single_select"
  | "multi_select"
  | "sequence"
  | "lead_select"
  | "vector_lab"
  | "point"
  | "region"
  | "caliper"
  | "march"
  | "compare"
  | "free_response"
  | "clinical_stage"
  | "hotspot_map"
  | "model_explore"
  | "numeric_entry"
  | "pairing"
  | "categorize";

export type FeedbackBranch = {
  id: string;
  when: "correct" | "partially_correct" | "incorrect" | "unsafe" | "not_assessable";
  heading: string;
  body: string;
  evidenceCue?: string;
  nextPrompt?: string;
};

export type AccessibilityContract = {
  instructions: string;
  keyboardAlternative: string;
  screenReaderSummary: string;
  reducedMotionAlternative?: string;
};

export type InteractionBase = {
  id: string;
  kind: InteractionKind;
  prompt: string;
  instructions: string;
  subskills: LearningSubskill[];
  requiredForCompletion: boolean;
  maxAttemptsBeforeScaffold: number;
  feedback: FeedbackBranch[];
  accessibility: AccessibilityContract;
};

export type SelectOption = {
  id: string;
  label: string;
  rationale: string;
};

export type SingleSelectInteraction = InteractionBase & {
  kind: "single_select";
  options: SelectOption[];
  correctOptionId: string;
};

export type MultiSelectInteraction = InteractionBase & {
  kind: "multi_select";
  options: SelectOption[];
  correctOptionIds: string[];
  minimumCorrect?: number;
  rejectExtraSelections?: boolean;
};

export type SequenceCard = {
  id: string;
  label: string;
  detail?: string;
};

export type SequenceInteraction = InteractionBase & {
  kind: "sequence";
  cards: SequenceCard[];
  correctOrder: string[];
};

export type LeadSelectInteraction = InteractionBase & {
  kind: "lead_select";
  selectionMode: "single" | "multiple" | "ordered";
  correctLeads: string[];
  allowedLeads?: string[];
  rejectExtraSelections?: boolean;
};

export type VectorPrediction = {
  lead: string;
  expected: "positive" | "negative" | "isoelectric";
};

export type VectorLabInteraction = InteractionBase & {
  kind: "vector_lab";
  initialAngleDeg: number;
  targetAngleDeg: number;
  toleranceDeg: number;
  targetLabel: string;
  predictions?: VectorPrediction[];
};

export type PointInteraction = InteractionBase & {
  kind: "point";
  concept: string;
  gradePrompt: string;
  allowedLeads?: string[];
};

export type RegionInteraction = InteractionBase & {
  kind: "region";
  concept: string;
  allowedLeads?: string[];
  minimumDurationMs?: number;
};

export type CaliperTarget = {
  source: "packet_measurement" | "authored_simulation" | "fixed";
  measurementKey?: string;
  valueMs?: number;
  toleranceMs: number;
  lead?: string;
  derive?: "rr_from_heart_rate";
};

export type CaliperInteraction = InteractionBase & {
  kind: "caliper";
  measurement: "rr" | "pr" | "qrs" | "qt" | "custom";
  target: CaliperTarget;
  requireBoundaryLabels?: boolean;
};

export type MarchInteraction = InteractionBase & {
  kind: "march";
  target: "p_waves" | "qrs_complexes" | "rr_intervals";
  minimumMarkers: number;
  expectedPattern: "regular" | "progressive" | "variable" | "dissociated";
  toleranceMs: number;
};

export type CompareDimension = {
  id: string;
  label: string;
  leftAnswer: string;
  rightAnswer: string;
};

export type CompareInteraction = InteractionBase & {
  kind: "compare";
  leftCaseConcept: string;
  rightCaseConcept: string;
  dimensions: CompareDimension[];
};

export type RubricCriterion = {
  id: string;
  label: string;
  acceptedConcepts: string[];
  required: boolean;
  misconceptionIfMissing?: string;
};

export type FreeResponseInteraction = InteractionBase & {
  kind: "free_response";
  responseLabel: string;
  placeholder: string;
  minimumCharacters: number;
  rubric: RubricCriterion[];
  sentenceFrame?: string;
};

export type ClinicalStage = {
  id: string;
  heading: string;
  revealCopy: string;
  question: string;
  options: SelectOption[];
  acceptableOptionIds: string[];
  unsafeOptionIds?: string[];
};

export type ClinicalStageInteraction = InteractionBase & {
  kind: "clinical_stage";
  stages: ClinicalStage[];
};

export type Hotspot = {
  id: string;
  label: string;
  xPercent: number;
  yPercent: number;
  description: string;
};

export type HotspotMapInteraction = InteractionBase & {
  kind: "hotspot_map";
  canvas: "torso" | "hexaxial" | "conduction_tree" | "waveform" | "heart";
  selectionMode: "single" | "multiple" | "ordered";
  hotspots: Hotspot[];
  correctHotspotIds: string[];
};

export type ModelFrame = {
  id: string;
  label: string;
  narration: string;
  vectorAngleDeg?: number;
  waveformLabel?: string;
  activeRegion?: "sa_node" | "atria" | "av_node" | "his_purkinje" | "ventricles" | "recovery";
};

export type ModelExploreInteraction = InteractionBase & {
  kind: "model_explore";
  model: "cardiac_cycle" | "vector_projection" | "av_ladder" | "bundle_activation" | "reentry" | "repolarization";
  frames: ModelFrame[];
  requiredFrameIds: string[];
};

export type NumericEntryInteraction = InteractionBase & {
  kind: "numeric_entry";
  label: string;
  unit: "bpm" | "ms" | "mV" | "degrees" | "boxes" | "ratio";
  target: {
    source: "packet_measurement" | "authored_simulation" | "fixed";
    measurementKey?: string;
    value?: number;
    tolerance: number;
    derive?: "rr_from_heart_rate";
  };
  minimum?: number;
  maximum?: number;
};

export type PairingItem = {
  id: string;
  label: string;
};

export type PairingInteraction = InteractionBase & {
  kind: "pairing";
  left: PairingItem[];
  right: PairingItem[];
  correctPairs: Record<string, string>;
};

export type CategorizeInteraction = InteractionBase & {
  kind: "categorize";
  items: PairingItem[];
  categories: PairingItem[];
  correctCategoryByItem: Record<string, string>;
};

export type LearningInteraction =
  | SingleSelectInteraction
  | MultiSelectInteraction
  | SequenceInteraction
  | LeadSelectInteraction
  | VectorLabInteraction
  | PointInteraction
  | RegionInteraction
  | CaliperInteraction
  | MarchInteraction
  | CompareInteraction
  | FreeResponseInteraction
  | ClinicalStageInteraction
  | HotspotMapInteraction
  | ModelExploreInteraction
  | NumericEntryInteraction
  | PairingInteraction
  | CategorizeInteraction;

export type InteractionEvidence = {
  interactionId: string;
  kind: InteractionKind;
  correct: boolean;
  partial: boolean;
  score: number;
  attempts: number;
  assistance: "independent" | "scaffolded";
  hintsUsed: number;
  response: unknown;
  selectedPoints?: ECGPoint[];
  measuredValueMs?: number;
  misconceptions: string[];
  feedbackBranch: FeedbackBranch["when"];
};

export type SourceReference = {
  document: string;
  section: string;
  requirementIds: string[];
};

export type CaseContract = {
  selectorLessonId: string;
  requestedConcept: string;
  minimumTier: "A" | "B";
  requiredEvidence: string[];
  requiredLeads?: string[];
  allowedUses: Array<"mechanism" | "worked_example" | "scored_recognition" | "measurement" | "transfer">;
  fallback: "authored_simulation" | "contrast_only" | "lock_scene";
  forbiddenClaims: string[];
};

export type VerbatimSceneCopy = {
  eyebrow: string;
  title: string;
  objective: string;
  openingTutorMessage: string;
  setup: string[];
  mechanismNarration: string[];
  clinicalConnectionHeading: string;
  clinicalConnectionBody: string;
  transitionIntoTask: string;
  completionHeading: string;
  completionBody: string;
  returnLabel: string;
};

export type SceneLayoutContract = {
  desktop: string;
  laptop: string;
  mobile: string;
  focusOrder: string[];
  viewerPlacement: "before_task" | "inside_task" | "beside_task" | "not_required";
};

export type TutorSceneContract = {
  socraticPrompts: string[];
  hintLadder: string[];
  tangentBridge: string;
  returnPrompt: string;
  caseUnavailablePrompt: string;
};

export type CrossModeHandoff = {
  mode: "train" | "rapid" | "clinical";
  label: string;
  /** The Guided objective this scene taught; retained for source traceability. */
  concept: string;
  subskill: LearningSubskill;
  supportLevel: "guided" | "faded" | "independent";
  /**
   * Exact executable contract at the destination. Broad Guided objectives do
   * not automatically equal a case-bank concept or an assessable receipt.
   * Rapid and Clinical handoffs must therefore name the task they can really
   * serve instead of relying on a best-effort alias after navigation.
   */
  destination?: {
    focus: string;
    subskill: LearningSubskill;
    receiptConcept?: string;
    secondaryConcept?: string;
    suggestedLength?: 5 | 10 | 25 | 50;
    pace?: "untimed" | "ward" | "emergency";
    lane?: "clinic" | "ward" | "ed";
    length?: 5 | 10;
  };
};

export type ProductionScene = {
  id: string;
  partId: string;
  minutes: number;
  source: SourceReference[];
  copy: VerbatimSceneCopy;
  layout: SceneLayoutContract;
  tutor: TutorSceneContract;
  caseContract?: CaseContract;
  interactions: LearningInteraction[];
  completionRule: {
    requiredInteractionIds: string[];
    minimumScore: number;
    requireIndependentAttempt: boolean;
    equivalentRetryOnCriticalMiss: boolean;
  };
  connections: {
    recallFrom: string;
    changesNow: string;
    reuseNext: string;
    clinicalUse: string;
  };
  handoffs: CrossModeHandoff[];
};

export type ProductionModule = {
  id: string;
  order: number;
  title: string;
  shortTitle: string;
  duration: string;
  outcome: string;
  prerequisiteIds: string[];
  accent: string;
  sourceRequirementIds: string[];
  scenes: ProductionScene[];
};
