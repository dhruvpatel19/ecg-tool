import type {
  CaseContract,
  FeedbackBranch,
  InteractionBase,
  LearningInteraction,
  LearningSubskill,
  ProductionModule,
  ProductionScene,
} from "@/lib/learning/interactionTypes";
import {
  caseContract,
  handoff,
  layout,
  productionScene,
  sceneCopy,
  source,
  tutor,
} from "@/lib/learning/modules/productionModuleHelpers";

export const M01_FORMAL_SWEEP = [
  "Calibration & quality",
  "Regularity & rate",
  "Atrial source & P–QRS",
  "Axis",
  "Timing: PR, QRS, QT span",
  "ST–T",
  "Synthesis",
] as const;

export type FoundationsBloomLevel = "understand" | "apply" | "analyze" | "evaluate" | "synthesize";

export type FoundationsSceneManifest = {
  sceneId: `S${number}`;
  objectiveId: string;
  bloom: FoundationsBloomLevel[];
  prerequisites: string[];
  requiredActions: string[];
  criticalRules: string[];
  evidenceCeiling: "none" | "guided" | "independent_immediate_candidate";
  transfer: string;
};

export const M01_SCENE_MANIFESTS: FoundationsSceneManifest[] = [
  { sceneId: "S0", objectiveId: "foundations_systematic_sweep", bloom: ["understand"], prerequisites: [], requiredActions: ["scope boundary", "seven-step route"], criticalRules: [], evidenceCeiling: "none", transfer: "S1" },
  { sceneId: "S1", objectiveId: "foundations_waveform_landmarks", bloom: ["understand", "apply"], prerequisites: ["S0"], requiredActions: ["explore activation", "mark P/QRS/T", "explain electrical versus mechanical"], criticalRules: ["P/T reversal requires an equivalent beat"], evidenceCeiling: "guided", transfer: "M4, M5, M8" },
  { sceneId: "S2", objectiveId: "foundations_calibration", bloom: ["apply"], prerequisites: ["S1"], requiredActions: ["read speed/gain", "measure time", "measure voltage", "contrast 50 mm/s"], criticalRules: ["measurement_without_valid_calibration"], evidenceCeiling: "guided", transfer: "every later measurement" },
  { sceneId: "S3", objectiveId: "foundations_signal_quality", bloom: ["analyze"], prerequisites: ["S1", "S2"], requiredActions: ["classify assessability by domain", "box artifact", "choose bounded claim"], criticalRules: ["unsupported diagnosis_urgency_or_treatment"], evidenceCeiling: "guided", transfer: "M3 and every clinical case" },
  { sceneId: "S4", objectiveId: "foundations_rate", bloom: ["apply", "analyze"], prerequisites: ["S1", "S2", "S3"], requiredActions: ["mark regular R waves", "choose regular method", "execute six-second irregular method"], criticalRules: ["rate_from_invalid_qrs_marks", "single_interval_method_on_irregular_strip"], evidenceCeiling: "guided", transfer: "M3 and M6" },
  { sceneId: "S5", objectiveId: "foundations_atrial_source", bloom: ["analyze"], prerequisites: ["S1", "S3", "S4"], requiredActions: ["mark P and QRS", "separate atrial source from P–QRS relationship", "communicate evidence"], criticalRules: ["definite_sinus_without_p_evidence"], evidenceCeiling: "guided", transfer: "M3, M4, M6" },
  { sceneId: "S6", objectiveId: "foundations_pr_qrs", bloom: ["apply", "analyze"], prerequisites: ["S1", "S2", "S3", "S5"], requiredActions: ["measure PR", "measure QRS", "classify each independently"], criticalRules: ["reviewed_wide_qrs_called_narrow", "reviewed_long_pr_called_within_reference"], evidenceCeiling: "guided", transfer: "M4 and M5" },
  { sceneId: "S7", objectiveId: "foundations_recovery", bloom: ["apply", "analyze"], prerequisites: ["S1", "S2", "S3", "S6"], requiredActions: ["mark baseline/J/T", "mark QT span", "order activation and recovery", "use lead-aware language"], criticalRules: ["confident_st_t_or_qt_claim_from_unreadable_boundaries"], evidenceCeiling: "guided", transfer: "M8 and M9" },
  { sceneId: "S8", objectiveId: "foundations_twelve_lead_navigation", bloom: ["understand", "analyze"], prerequisites: ["S5", "S7"], requiredActions: ["locate anchor leads", "interpret representation", "compare V1–V6", "explain one event/twelve views"], criticalRules: ["rhythm_inferred_from_median_tiles"], evidenceCeiling: "guided", transfer: "M2, M7, M9" },
  { sceneId: "S9", objectiveId: "foundations_axis", bloom: ["analyze"], prerequisites: ["S6", "S8"], requiredActions: ["predict vector projection", "apply I/aVF", "use II for leftward refinement"], criticalRules: ["coarse_axis_direction_reversed"], evidenceCeiling: "guided", transfer: "M2 and M7" },
  { sceneId: "S10", objectiveId: "foundations_systematic_sweep", bloom: ["understand", "apply"], prerequisites: ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"], requiredActions: ["predict before reveal", "reconstruct seven-step sweep", "calibrate claim ceiling"], criticalRules: [], evidenceCeiling: "none", transfer: "S11" },
  { sceneId: "S11", objectiveId: "foundations_systematic_sweep", bloom: ["apply", "analyze", "synthesize"], prerequisites: ["S10"], requiredActions: ["complete all seven domains", "preserve not-assessable states", "write evidence-linked synthesis"], criticalRules: ["claim_attached_to_wrong_lead_wave_or_interval", "unsupported_diagnosis_urgency_or_treatment"], evidenceCeiling: "guided", transfer: "Focused and Rapid practice" },
  { sceneId: "S12", objectiveId: "foundations_systematic_sweep", bloom: ["analyze", "evaluate", "synthesize"], prerequisites: ["S11"], requiredActions: ["two integrated reads", "attach claims to evidence", "calibrate confidence"], criticalRules: ["claim_attached_to_wrong_lead_wave_or_interval", "unsupported_diagnosis_urgency_or_treatment"], evidenceCeiling: "independent_immediate_candidate", transfer: "M2 and later mixed retention" },
];

const auditSource = (sceneId: string, requirementIds: string[]) => [
  source(`M01.${sceneId}`, requirementIds, "docs/storyboards/VERBATIM_M01_M03.md"),
  source(`Installments 7–9 · ${sceneId}`, requirementIds, "docs/module-audit/foundations/gpt-pro-review/normalized/08-8-multimodal-ecg-grounded-assessment-blueprint.md"),
];

const interactionBase = (
  id: string,
  prompt: string,
  instructions: string,
  subskills: LearningSubskill[],
  correct: string,
  partial: string,
  incorrect: string,
  cue: string,
  maxAttemptsBeforeScaffold = 1,
): Omit<InteractionBase, "kind"> => ({
  id,
  prompt,
  instructions,
  subskills,
  requiredForCompletion: true,
  maxAttemptsBeforeScaffold,
  feedback: [
    { id: "correct", when: "correct", heading: "That’s it", body: `${correct} Carry that same reasoning into the next example.` },
    { id: "partial", when: "partially_correct", heading: "Almost there", body: `${partial} One part still needs support from the tracing. ${cue}`, evidenceCue: cue },
    { id: "incorrect", when: "incorrect", heading: "Take another look", body: `${incorrect} ${cue}`, evidenceCue: cue },
    { id: "not-assessable", when: "not_assessable", heading: "This cannot be judged here", body: "This view does not show enough to answer that part safely. Keep what you can support and mark the rest as not assessable." },
  ] satisfies FeedbackBranch[],
  accessibility: {
    instructions,
    keyboardAlternative: "Use the labeled controls below the visual. Every pointer action has an equivalent button, slider, select, or text control.",
    screenReaderSummary: prompt,
    reducedMotionAlternative: "The same information is available as static numbered states; no motion is required.",
  },
});

const commonLayout = (viewer: boolean) => layout({
  desktop: viewer ? "ECG canvas fills the main pane; one active question and evidence review stay in the response rail." : "The active model or task fills the main pane; the response rail preserves progress and feedback.",
  laptop: "The task remains primary with context collapsed into progressive disclosure.",
  mobile: "ECG or authored visual appears first, followed by one full-width action and its feedback. No horizontal page scrolling is required.",
  focusOrder: ["scene heading", "learning setup", "ECG or authored visual", "active task", "feedback", "tutor", "navigation"],
  viewerPlacement: viewer ? "before_task" : "inside_task",
});

const sceneTutor = (opening: string, hints: string[], returnPrompt: string) => tutor(
  [opening],
  hints,
  "I can clarify the rule, inspect the evidence you chose, or ask one retrieval question. I cannot reveal hidden case truth or change your score.",
  returnPrompt,
);

type SceneDefinition = {
  id: `S${number}`;
  partId: string;
  minutes: number;
  title: string;
  objective: string;
  setup: string[];
  mechanism: string[];
  clinicalHeading: string;
  clinicalBody: string;
  transition: string;
  completionBody: string;
  requirements: string[];
  interactions: LearningInteraction[];
  caseContract?: CaseContract;
  minimumScore?: number;
  independent?: boolean;
  connections: ProductionScene["connections"];
  handoffs: ProductionScene["handoffs"];
  tutorPrompt: string;
  hints: string[];
};

const buildScene = (definition: SceneDefinition) => productionScene({
  id: definition.id,
  partId: definition.partId,
  minutes: definition.minutes,
  source: auditSource(definition.id, definition.requirements),
  copy: sceneCopy({
    eyebrow: `Foundations · ${Number(definition.id.slice(1)) + 1} of 13`,
    title: definition.title,
    objective: definition.objective,
    openingTutorMessage: `${definition.tutorPrompt} I’ll keep your current question and answer in view.`,
    setup: definition.setup,
    mechanismNarration: definition.mechanism,
    clinicalConnectionHeading: definition.clinicalHeading,
    clinicalConnectionBody: definition.clinicalBody,
    transitionIntoTask: definition.transition,
    completionHeading: definition.id === "S12" ? "Foundations complete" : "Lesson complete",
    completionBody: definition.completionBody,
    returnLabel: `Return to ${definition.id} · current question`,
  }),
  layout: commonLayout(Boolean(definition.caseContract)),
  tutor: sceneTutor(definition.tutorPrompt, definition.hints, `Return to ${definition.id} and continue the current question.`),
  caseContract: definition.caseContract,
  learningContract: (() => {
    const manifest = M01_SCENE_MANIFESTS.find((item) => item.sceneId === definition.id);
    if (!manifest) throw new Error(`Missing Foundations manifest for ${definition.id}`);
    return {
      objectiveId: manifest.objectiveId,
      bloom: manifest.bloom,
      prerequisiteSceneIds: manifest.prerequisites,
      evidenceCeiling: manifest.evidenceCeiling,
      criticalRules: manifest.criticalRules,
    };
  })(),
  interactions: definition.interactions,
  completionRule: {
    requiredInteractionIds: definition.interactions.filter((item) => item.requiredForCompletion).map((item) => item.id),
    minimumScore: definition.minimumScore ?? 0.8,
    requireIndependentAttempt: definition.independent ?? false,
    equivalentRetryOnCriticalMiss: true,
  },
  connections: definition.connections,
  handoffs: definition.handoffs,
});

const s0: LearningInteraction[] = [
  {
    ...interactionBase("m01-s0-sweep", "Put the ECG reading checkpoints in order.", "Move each checkpoint into the sequence you would use before writing your final interpretation.", ["synthesize"], "You started with the signal, worked through the tracing in a consistent order, and synthesized last.", "Several checkpoints are already in a useful position.", "The order matters because each later conclusion depends on observations made earlier.", "Start by checking the signal; combine your findings only after the individual checks."),
    kind: "sequence",
    cards: M01_FORMAL_SWEEP.map((label, index) => ({ id: `step-${index + 1}`, label })),
    correctOrder: M01_FORMAL_SWEEP.map((_, index) => `step-${index + 1}`),
  },
  {
    ...interactionBase("m01-s0-scope", "Which habits make an ECG interpretation reliable?", "Select every habit you should carry into a real ECG read.", ["calibrate_confidence"], "You protected the interpretation from an unreliable signal, unsupported guesses, and premature diagnosis.", "You kept at least one reliable habit, but another important safeguard is missing.", "A consistent read separates what is visible from what is only suspected.", "Check the signal first, state uncertainty precisely, and use the clinical story before deciding what a pattern means."),
    kind: "multi_select",
    options: [
      { id: "signal", label: "Check calibration and signal quality before making measurements.", rationale: "A faulty ruler or unreadable signal can distort every later conclusion." },
      { id: "describe", label: "Describe what the tracing supports before naming a diagnosis.", rationale: "Observation-first language keeps the interpretation tied to visible evidence." },
      { id: "na", label: "State which feature is not assessable instead of guessing or discarding the whole tracing.", rationale: "Uncertainty should be specific to the feature the ECG cannot show." },
      { id: "regular", label: "When a rhythm looks regular, estimate the rate before checking calibration.", rationale: "Rate calculations still depend on valid paper speed and a readable signal." },
      { id: "noise", label: "If one lead is noisy, treat every part of the ECG as uninterpretable.", rationale: "A local limitation does not automatically erase evidence available elsewhere." },
    ],
    correctOptionIds: ["signal", "describe", "na"],
    rejectExtraSelections: true,
  },
];

const s1: LearningInteraction[] = [
  {
    ...interactionBase("m01-s1-cycle", "Explore how one electrical cycle becomes P, QRS, and T.", "Visit every frame; activation and recovery are shown separately from mechanical contraction.", ["explain_mechanism"], "You connected atrial activation, ventricular activation, and ventricular recovery to the three principal waveform components.", "Most frames are explored.", "Waveform labels describe electrical events, not a direct picture of chamber squeeze.", "Visit each numbered electrical frame."),
    kind: "model_explore",
    model: "cardiac_cycle",
    frames: [
      { id: "sa", label: "Atrial activation begins", narration: "An atrial activation wave begins near the sinus node and contributes to the P wave.", waveformLabel: "P begins", activeRegion: "sa_node" },
      { id: "atria", label: "Atria activate", narration: "Atrial activation spreads; the surface projection forms the P wave.", waveformLabel: "P wave", activeRegion: "atria" },
      { id: "av", label: "AV delay", narration: "Conduction through the AV node and His-Purkinje system occupies the PR span before ventricular activation.", waveformLabel: "PR span", activeRegion: "av_node" },
      { id: "qrs", label: "Ventricles activate", narration: "Rapid ventricular depolarization produces the QRS complex.", waveformLabel: "QRS", activeRegion: "ventricles" },
      { id: "t", label: "Ventricles recover", narration: "Ventricular repolarization contributes to the T wave.", waveformLabel: "T wave", activeRegion: "recovery" },
    ],
    requiredFrameIds: ["sa", "atria", "av", "qrs", "t"],
  },
  {
    ...interactionBase("m01-s1-landmarks", "Mark P, QRS, and T on a new lead-II beat.", "Choose a target, then click the waveform or use the keyboard cursor and Place target.", ["localize"], "All three landmarks are attached to the correct electrical deflections.", "At least one landmark is correctly localized.", "One or more labels landed on the wrong deflection.", "Use sequence and shape: small atrial deflection, rapid ventricular complex, then recovery wave.", 2),
    kind: "waveform_lab",
    trace: "alternate_beat",
    lead: "II",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "point_targets",
    targets: [
      { id: "p", label: "P wave", timeMs: 240 },
      { id: "qrs", label: "QRS complex", timeMs: 430 },
      { id: "t", label: "T wave", timeMs: 715 },
    ],
    requiredTargetIds: ["p", "qrs", "t"],
    toleranceMs: 65,
  },
  {
    ...interactionBase("m01-s1-mechanism", "What do P, QRS, and T represent most directly?", "Choose the most defensible statement.", ["discriminate", "explain_mechanism"], "The ECG records changing surface voltage from electrical activation and recovery.", "You kept the answer electrical but need greater precision.", "The ECG is not a direct pressure, contraction, or blood-flow tracing.", "Choose electrical activation/recovery rather than mechanical output."),
    kind: "single_select",
    options: [
      { id: "electrical", label: "Surface-voltage projections of electrical activation and recovery.", rationale: "Correct." },
      { id: "contraction", label: "Direct measurements of atrial and ventricular contraction strength.", rationale: "Mechanical function is not measured directly." },
      { id: "flow", label: "The direction and volume of blood flow through each chamber.", rationale: "Blood flow is not the recorded signal." },
      { id: "pressure", label: "Continuous atrial and ventricular pressure curves.", rationale: "The ECG is not a pressure transducer." },
    ],
    correctOptionId: "electrical",
  },
];

const s2: LearningInteraction[] = [
  {
    ...interactionBase("m01-s2-grid-pairs", "Pair the standard calibration values with their grid meaning.", "Use 25 mm/s and 10 mm/mV.", ["measure"], "Time and voltage scales are correctly paired.", "Some grid relationships are correct.", "A time or voltage unit was attached to the wrong box size.", "At 25 mm/s: 1 small box is 40 ms and 1 large box is 200 ms; at 10 mm/mV: 10 mm is 1 mV."),
    kind: "pairing",
    left: [
      { id: "small-time", label: "1 small horizontal box" },
      { id: "large-time", label: "1 large horizontal box" },
      { id: "vertical", label: "10 mm vertically" },
      { id: "speed", label: "Standard paper speed" },
    ],
    right: [
      { id: "40ms", label: "40 ms" },
      { id: "200ms", label: "200 ms" },
      { id: "1mv", label: "1 mV" },
      { id: "25", label: "25 mm/s" },
    ],
    correctPairs: { "small-time": "40ms", "large-time": "200ms", vertical: "1mv", speed: "25" },
  },
  {
    ...interactionBase("m01-s2-horizontal", "Place a 200 ms horizontal span on the calibrated trace.", "Place the start and end boundaries. The ruler is 25 mm/s.", ["localize", "measure"], "Both boundaries enclose one large box, or 200 ms.", "One boundary is accurate.", "The selected span does not yet represent 200 ms at 25 mm/s.", "One large horizontal box equals 200 ms."),
    kind: "waveform_lab",
    trace: "calibration_beat",
    lead: "II",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "interval",
    targets: [{ id: "span", label: "200 ms span", startMs: 700, endMs: 900 }],
    requiredTargetIds: ["span"],
    toleranceMs: 30,
    showCalibration: true,
  },
  {
    ...interactionBase("m01-s2-fast-paper", "At 50 mm/s, how long is one small horizontal box?", "Enter the duration in milliseconds.", ["measure", "explain_mechanism"], "Doubling paper speed halves the time represented by each box.", "Your value moved in the right direction.", "The box duration must change when paper speed changes.", "At 50 mm/s, 1 mm passes in 0.02 s."),
    kind: "numeric_entry",
    label: "One small box at 50 mm/s",
    unit: "ms",
    target: { source: "fixed", value: 20, tolerance: 1 },
    minimum: 1,
    maximum: 200,
  },
  {
    ...interactionBase("m01-s2-units", "Sort each item by what it measures.", "Keep time, voltage, and acquisition settings separate.", ["discriminate"], "Every item is attached to the correct measurement domain.", "Most units are correctly separated.", "A setting, time unit, or voltage unit is conflated.", "Milliseconds describe time; millivolts voltage; mm/s speed; mm/mV gain."),
    kind: "categorize",
    items: [
      { id: "ms", label: "milliseconds" },
      { id: "mv", label: "millivolts" },
      { id: "mms", label: "mm/s" },
      { id: "mmmv", label: "mm/mV" },
    ],
    categories: [
      { id: "time", label: "Time" },
      { id: "voltage", label: "Voltage" },
      { id: "speed", label: "Paper speed" },
      { id: "gain", label: "Gain" },
    ],
    correctCategoryByItem: { ms: "time", mv: "voltage", mms: "speed", mmmv: "gain" },
  },
];

const s3: LearningInteraction[] = [
  {
    ...interactionBase("m01-s3-domains", "Classify what each signal-quality observation permits.", "Assessability is task-specific; a strip may support one domain and not another.", ["discriminate", "calibrate_confidence"], "Each claim is bounded to the representation that can support it.", "Several domain boundaries are correct.", "A broad quality label would hide which domain remains readable.", "Ask separately about rate, P waves, intervals, and ST–T rather than calling the entire ECG good or bad."),
    kind: "categorize",
    items: [
      { id: "qrs-clear", label: "QRS peaks are clear; baseline wanders" },
      { id: "p-hidden", label: "QRS is clear; atrial activity is obscured" },
      { id: "median", label: "Only aligned median morphology tiles are shown" },
      { id: "clean", label: "Calibration and all required landmarks are readable" },
    ],
    categories: [
      { id: "rate-only", label: "Rate/spacing may be assessable" },
      { id: "source-na", label: "Atrial source not assessable" },
      { id: "morph-only", label: "Morphology only; no rhythm timing" },
      { id: "domain-ready", label: "Proceed with named domains" },
    ],
    correctCategoryByItem: { "qrs-clear": "rate-only", "p-hidden": "source-na", median: "morph-only", clean: "domain-ready" },
  },
  {
    ...interactionBase("m01-s3-artifact", "Box the interval that most limits fine waveform interpretation.", "Place a start and end boundary around the broad artifact interval; preserve readable signal outside it.", ["localize", "discriminate"], "The region captures the limiting artifact without covering most valid signal.", "One edge of the artifact region is useful.", "The selection misses the limiting noise or erases too much readable tracing.", "The artifact occupies roughly the middle third of this six-second strip."),
    kind: "waveform_lab",
    trace: "artifact_strip",
    lead: "II",
    durationMs: 6000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "region",
    targets: [{ id: "artifact", label: "Limiting artifact", startMs: 2050, endMs: 3220 }],
    requiredTargetIds: ["artifact"],
    toleranceMs: 260,
  },
  {
    ...interactionBase("m01-s3-claim", "The QRS peaks remain visible, but P waves and the baseline are obscured. What is the best next statement?", "Choose the safest conclusion the tracing supports, not a diagnosis.", ["discriminate", "calibrate_confidence"], "You preserved useful rate evidence while withholding unsupported source and ST–T claims.", "You recognized at least one limitation.", "A definite rhythm or ST–T statement exceeds the visible evidence.", "State what remains assessable and name what cannot be assessed."),
    kind: "single_select",
    options: [
      { id: "bounded", label: "Ventricular spacing may be estimated; atrial source and ST–T are not assessable here.", rationale: "Correct." },
      { id: "normal", label: "The ECG is normal because the QRS peaks are regular.", rationale: "Regular QRS timing does not establish all domains." },
      { id: "af", label: "This proves atrial fibrillation because P waves are not visible.", rationale: "Unavailable P evidence is not absent organized atrial activity." },
      { id: "repeat-none", label: "No part of the tracing can be used for any purpose.", rationale: "QRS timing remains visible." },
    ],
    correctOptionId: "bounded",
  },
];

const s4: LearningInteraction[] = [
  {
    ...interactionBase("m01-s4-regular-marks", "Mark four consecutive QRS complexes before calculating rate.", "Click each R/QRS center on this regular six-second teaching strip. Do not mark P or T waves.", ["localize", "measure"], "Four consecutive ventricular events are correctly anchored.", "Some ventricular events are correctly marked.", "One or more markers do not identify a QRS complex.", "Use the narrow, rapid ventricular deflection—not the broader T wave.", 2),
    kind: "waveform_lab",
    trace: "regular_strip",
    lead: "II",
    durationMs: 6000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "march",
    targets: [450, 1250, 2050, 2850, 3650, 4450, 5250].map((timeMs, index) => ({ id: `r${index + 1}`, label: `QRS ${index + 1}`, timeMs })),
    requiredTargetIds: ["r1", "r2", "r3", "r4", "r5", "r6", "r7"],
    toleranceMs: 85,
    minimumMarkers: 4,
    expectedPattern: "regular",
  },
  {
    ...interactionBase("m01-s4-regular-method", "Which rate method best fits the regular strip you just marked?", "Choose the method and explainable geometry, not a memorized report value.", ["discriminate", "explain_mechanism"], "A stable R–R interval supports an interval-based estimate.", "You recognized regularity but not the most efficient geometry.", "A six-second average is valid but less precise for this clearly regular teaching strip.", "Use 300 divided by large boxes between consecutive R waves at 25 mm/s."),
    kind: "single_select",
    options: [
      { id: "large-box", label: "Use 300 ÷ large boxes between consecutive R waves.", rationale: "Correct for a regular rhythm at 25 mm/s." },
      { id: "six-only", label: "Always count six seconds and multiply by ten, even when regular.", rationale: "Possible but not the preferred interval estimate here." },
      { id: "p-count", label: "Count P waves in one second and multiply by sixty.", rationale: "That estimates atrial events, not necessarily ventricular rate." },
      { id: "qrs-width", label: "Divide QRS duration into 60 seconds.", rationale: "QRS width is not cycle length." },
    ],
    correctOptionId: "large-box",
  },
  {
    ...interactionBase("m01-s4-regular-rate", "The R–R interval spans four large boxes at 25 mm/s. Estimate the ventricular rate.", "Enter the result in beats per minute.", ["measure"], "Four large boxes correspond to about 75 beats/min.", "Your arithmetic is close.", "The calculation does not match the regular large-box method.", "Compute 300 ÷ 4."),
    kind: "numeric_entry",
    label: "Estimated ventricular rate",
    unit: "bpm",
    target: { source: "fixed", value: 75, tolerance: 5 },
    minimum: 20,
    maximum: 300,
  },
  {
    ...interactionBase("m01-s4-irregular", "Mark every QRS in this irregular six-second teaching strip.", "Use the full six-second window. The result will support a count ×10 average, not a one-interval rate.", ["localize", "measure", "discriminate"], "All eight QRS complexes are marked, supporting an average ventricular rate near 80 beats/min.", "Several QRS complexes are correctly marked.", "Missing QRS complexes or marking T waves would change the six-second estimate.", "Scan left to right once; count only rapid ventricular complexes.", 2),
    kind: "waveform_lab",
    trace: "irregular_strip",
    lead: "II",
    durationMs: 6000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "march",
    targets: [380, 1050, 1840, 2500, 3440, 4170, 5070, 5750].map((timeMs, index) => ({ id: `ir${index + 1}`, label: `QRS ${index + 1}`, timeMs })),
    requiredTargetIds: ["ir1", "ir2", "ir3", "ir4", "ir5", "ir6", "ir7", "ir8"],
    toleranceMs: 85,
    minimumMarkers: 8,
    expectedPattern: "variable",
  },
];

const s5: LearningInteraction[] = [
  {
    ...interactionBase("m01-s5-p-qrs", "Mark a repeatable P wave and the next QRS on this teaching beat.", "Place the P marker first, then the QRS marker. Source and conduction relationship will be judged separately afterward.", ["localize"], "The atrial deflection and following ventricular complex are correctly identified.", "One of the two events is correctly localized.", "The markers do not yet establish a chronological P-to-next-QRS relationship.", "Find the small atrial deflection before the rapid QRS."),
    kind: "waveform_lab",
    trace: "normal_beat",
    lead: "II",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "point_targets",
    targets: [
      { id: "p", label: "P wave", timeMs: 250 },
      { id: "qrs", label: "Next QRS", timeMs: 440 },
    ],
    requiredTargetIds: ["p", "qrs"],
    toleranceMs: 60,
  },
  {
    ...interactionBase("m01-s5-separate", "Separate atrial-source evidence from the P–QRS relationship.", "Assign each observation to the question it actually answers.", ["discriminate", "explain_mechanism"], "Source morphology and conduction relationship remain distinct evidence domains.", "Most observations are assigned correctly.", "One-to-one conduction does not, by itself, prove a sinus atrial source.", "Lead-II/aVR P direction speaks to source; chronological links speak to P–QRS relationship."),
    kind: "categorize",
    items: [
      { id: "ii", label: "Repeatable P waves are upright in lead II" },
      { id: "avr", label: "Aligned P waves are negative in aVR" },
      { id: "one", label: "Each visible P is followed by the next QRS" },
      { id: "stable", label: "The P-to-QRS timing is stable across beats" },
    ],
    categories: [
      { id: "source", label: "Atrial-source evidence" },
      { id: "relationship", label: "P–QRS relationship evidence" },
    ],
    correctCategoryByItem: { ii: "source", avr: "source", one: "relationship", stable: "relationship" },
  },
  {
    ...interactionBase("m01-s5-claim", "P waves are not visible in the available leads, while QRS complexes are regular. Which statement is defensible?", "Choose the calibrated two-part conclusion.", ["discriminate", "calibrate_confidence"], "You withheld a definite source claim while preserving the visible ventricular observation.", "You recognized some uncertainty.", "Regular QRS timing cannot prove a sinus P-wave pattern when atrial activity is unavailable.", "Report atrial source as not assessable; state the separate ventricular observation."),
    kind: "single_select",
    options: [
      { id: "na", label: "Atrial source is not assessable here; ventricular timing appears regular in this segment.", rationale: "Correct." },
      { id: "sinus", label: "Sinus rhythm is confirmed because the ventricular rhythm is regular.", rationale: "Source requires P-wave evidence." },
      { id: "junctional", label: "A junctional rhythm is confirmed because P waves are not visible.", rationale: "Nonvisibility is not diagnostic." },
      { id: "af", label: "Atrial fibrillation is confirmed because P waves are not visible.", rationale: "AF requires more than unavailable P waves." },
    ],
    correctOptionId: "na",
  },
];

const s6: LearningInteraction[] = [
  {
    ...interactionBase("m01-s6-pr-span", "Measure PR from P onset to QRS onset.", "Place both boundaries on the long-PR practice beat. The answer stays hidden until you submit.", ["localize", "measure"], "Both PR boundaries are correct and the span is about 300 ms.", "One PR boundary is correctly placed.", "PR must begin at P onset and end at QRS onset.", "Do not measure from the P peak or to the R peak."),
    kind: "waveform_lab",
    trace: "long_pr_beat",
    lead: "II",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "interval",
    targets: [{ id: "pr", label: "PR interval", startMs: 140, endMs: 440 }],
    requiredTargetIds: ["pr"],
    toleranceMs: 35,
  },
  {
    ...interactionBase("m01-s6-pr-value", "Enter the PR value you measured and classify it.", "At standard adult teaching reference, 120–200 ms is the usual reference span; this task asks only for the interval category.", ["measure", "discriminate"], "The value and long-PR category agree with the boundaries.", "Either the value or category is aligned.", "The category must follow the measured span, not a later block label.", "A PR near 300 ms is long; do not name a block in this Foundations task."),
    kind: "single_select",
    options: [
      { id: "300-long", label: "About 300 ms; long PR.", rationale: "Correct." },
      { id: "300-usual", label: "About 300 ms; within the usual reference span.", rationale: "The category conflicts with the value." },
      { id: "160-long", label: "About 160 ms; long PR.", rationale: "Both the value and category conflict." },
      { id: "first-degree", label: "First-degree AV block; no interval value is needed.", rationale: "Foundations records the measured observation before the later diagnosis." },
    ],
    correctOptionId: "300-long",
  },
  {
    ...interactionBase("m01-s6-qrs-span", "Measure QRS onset to final QRS offset.", "Place both boundaries around the entire wide QRS, including the terminal deflection.", ["localize", "measure"], "The entire QRS is enclosed at about 120 ms.", "One boundary is correct.", "Stopping before the terminal deflection underestimates QRS duration.", "Start at the first departure from baseline and finish at the final return."),
    kind: "waveform_lab",
    trace: "wide_qrs_beat",
    lead: "V1",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "interval",
    targets: [{ id: "qrs", label: "QRS duration", startMs: 405, endMs: 520 }],
    requiredTargetIds: ["qrs"],
    toleranceMs: 30,
  },
  {
    ...interactionBase("m01-s6-categories", "Which statement preserves both duration and diagnostic boundaries?", "Choose the descriptive statement only.", ["discriminate", "calibrate_confidence"], "The wide QRS observation is reported without inventing a bundle diagnosis.", "You preserved either width or the diagnostic boundary.", "Narrow does not mean otherwise normal, and wide alone does not identify a conduction pathway.", "Report duration/category first; morphology is a separate later question."),
    kind: "single_select",
    options: [
      { id: "wide-bounded", label: "QRS is about 120 ms and wide; a specific conduction label needs morphology evidence.", rationale: "Correct." },
      { id: "rbbb", label: "Any QRS at 120 ms proves right bundle-branch block.", rationale: "Width alone is insufficient." },
      { id: "normal", label: "A narrow QRS means the entire ECG is normal.", rationale: "Narrow is one domain only." },
      { id: "axis", label: "QRS duration establishes the frontal axis.", rationale: "Axis uses lead polarity, not duration." },
    ],
    correctOptionId: "wide-bounded",
  },
];

const s7: LearningInteraction[] = [
  {
    ...interactionBase("m01-s7-landmarks", "Mark the TP baseline, J point, and T wave on the practice beat.", "Place each named target; use a stable reference segment rather than an arbitrary zero line.", ["localize"], "Baseline, end of QRS, and recovery wave are correctly anchored.", "At least one recovery landmark is correct.", "An ST or T conclusion needs a correctly located baseline and J point.", "Baseline is the stable segment before the next P; J is the end of QRS; T is the later recovery wave."),
    kind: "waveform_lab",
    trace: "st_t_beat",
    lead: "II",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "point_targets",
    targets: [
      { id: "baseline", label: "TP baseline", timeMs: 90 },
      { id: "j", label: "J point", timeMs: 485 },
      { id: "t", label: "T wave", timeMs: 725 },
    ],
    requiredTargetIds: ["baseline", "j", "t"],
    toleranceMs: 60,
  },
  {
    ...interactionBase("m01-s7-qt", "Mark the QT span on the same practice beat.", "QT begins at QRS onset and ends at the end of the T wave—not the T peak.", ["localize", "measure"], "The selected span includes depolarization and recovery through T-wave end.", "One endpoint is correct.", "QT must begin with QRS onset and end where the T wave returns to baseline.", "Do not stop at the T peak."),
    kind: "waveform_lab",
    trace: "st_t_beat",
    lead: "II",
    durationMs: 1000,
    paperSpeedMmSec: 25,
    gainMmMv: 10,
    task: "interval",
    targets: [{ id: "qt", label: "QT span", startMs: 405, endMs: 880 }],
    requiredTargetIds: ["qt"],
    toleranceMs: 45,
  },
  {
    ...interactionBase("m01-s7-sequence", "Order the electrical events that frame ST–T interpretation.", "Build activation before recovery and attach the surface landmark to each transition.", ["explain_mechanism", "synthesize"], "Ventricular activation, J point/ST span, then ventricular recovery are ordered correctly.", "Part of the activation-to-recovery chain is intact.", "ST–T interpretation loses meaning if activation and recovery are reversed.", "QRS activation ends at J; ST follows; T represents recovery."),
    kind: "sequence",
    cards: [
      { id: "qrs", label: "Ventricular activation produces QRS" },
      { id: "j", label: "QRS ends at the J point" },
      { id: "st", label: "ST is judged relative to a named baseline" },
      { id: "t", label: "The T wave reflects ventricular recovery" },
    ],
    correctOrder: ["qrs", "j", "st", "t"],
  },
  {
    ...interactionBase("m01-s7-lead-aware", "Which T-wave statement is appropriately lead-aware?", "Avoid a universal same-direction shortcut.", ["discriminate", "calibrate_confidence"], "You used lead identity and readable morphology instead of a universal polarity rule.", "You recognized that lead context matters.", "T-wave expectations vary by lead and patient context.", "State the lead, direction/shape, and uncertainty; do not infer a cause here."),
    kind: "single_select",
    options: [
      { id: "aware", label: "Describe T direction and shape in each named lead; aVR is often negative and V1 may vary.", rationale: "Correct." },
      { id: "same", label: "T must always point in the same direction as the QRS in every lead.", rationale: "This shortcut is not universally true." },
      { id: "positive", label: "A negative T wave always proves acute ischemia.", rationale: "Cause requires distribution and context." },
      { id: "qt", label: "The T-wave peak is always the QT endpoint.", rationale: "QT ends at T-wave end." },
    ],
    correctOptionId: "aware",
  },
];

const s8: LearningInteraction[] = [
  {
    ...interactionBase("m01-s8-anchors", "Locate five anchor leads on the displayed 12-lead ECG.", "Use printed lead labels. Select II, aVR, V1, V3, and V6.", ["localize"], "The anchor leads span inferior, opposing frontal, and early-to-late precordial views.", "Several anchor leads are correct.", "Waveform shape is not a safe substitute for the printed lead label.", "Find II and aVR first, then V1, V3, and V6 across the chest-lead sequence."),
    kind: "lead_select",
    selectionMode: "multiple",
    correctLeads: ["II", "aVR", "V1", "V3", "V6"],
    rejectExtraSelections: true,
  },
  {
    ...interactionBase("m01-s8-representation", "What can an aligned median-morphology study view support?", "Select every claim that remains valid for that representation.", ["discriminate", "calibrate_confidence"], "You preserved morphology comparison while withholding beat-to-beat and simultaneity claims.", "At least one representation boundary is correct.", "Median tiles summarize morphology; they do not reconstruct rhythm timing or prove panels are simultaneous.", "Allow cross-lead morphology comparison; reject regularity, beat variation, and cross-panel timing."),
    kind: "multi_select",
    options: [
      { id: "morphology", label: "Compare representative waveform morphology across named leads.", rationale: "Correct." },
      { id: "progression", label: "Explore the broad R/S pattern from V1 through V6 when QRS windows are visible.", rationale: "Correct as guided morphology exploration." },
      { id: "regularity", label: "Prove beat-to-beat regularity across the median tiles.", rationale: "A median composite is not a continuous sequence." },
      { id: "simultaneous", label: "Assume every displayed panel was recorded at the same instant.", rationale: "Display timing metadata is required." },
    ],
    correctOptionIds: ["morphology", "progression"],
    rejectExtraSelections: true,
  },
  {
    ...interactionBase("m01-s8-progression", "Pair each precordial region with its broad R/S expectation in a typical teaching example.", "Treat this as a guided pattern, not a universal normality test.", ["recognize", "discriminate"], "Early, transition, and late precordial patterns are correctly distinguished.", "Most regions are paired correctly.", "R/S progression varies and requires reviewed QRS windows before exact transition scoring.", "V1–V2 often begin S-dominant, middle leads transition, V5–V6 are often R-dominant."),
    kind: "pairing",
    left: [
      { id: "early", label: "V1–V2" },
      { id: "middle", label: "V3–V4" },
      { id: "late", label: "V5–V6" },
    ],
    right: [
      { id: "s", label: "Often S-dominant" },
      { id: "transition", label: "Common transition region; variation exists" },
      { id: "r", label: "Often R-dominant" },
    ],
    correctPairs: { early: "s", middle: "transition", late: "r" },
  },
  {
    ...interactionBase("m01-s8-explain", "Explain why the same heartbeat looks different across the twelve leads.", "Include one evolving electrical process and multiple directed views. Do not describe twelve separate cardiac events.", ["explain_mechanism", "synthesize"], "Your explanation connects one evolving event to different lead projections.", "You included either the shared event or the different viewpoints.", "The heart does not restart for each displayed lead.", "Use both ideas: one evolving electrical process and multiple directed viewpoints."),
    kind: "free_response",
    responseLabel: "One-event, twelve-view explanation",
    placeholder: "The same evolving electrical process appears different because each lead …",
    minimumCharacters: 45,
    sentenceFrame: "One evolving electrical process + different directed lead views",
    rubric: [
      { id: "one-event", label: "One evolving event", acceptedConcepts: ["same event", "one event", "same electrical process", "one evolving electrical process"], required: true, misconceptionIfMissing: "twelve_events_misconception" },
      { id: "views", label: "Different directed views", acceptedConcepts: ["different views", "different directions", "different angles", "different projections"], required: true, misconceptionIfMissing: "lead_viewpoint_missing" },
    ],
  },
];

const s9: LearningInteraction[] = [
  {
    ...interactionBase("m01-s9-vector", "Aim the mean frontal QRS vector toward +60° and predict lead I and aVF polarity.", "Use projection geometry before applying the quadrant rule.", ["explain_mechanism", "discriminate"], "A +60° vector points toward both lead I and aVF, so both are positive.", "The vector or one lead polarity is correct.", "Axis classification should follow the direction of the full QRS vector, not a single peak or T wave.", "Lead I is 0° and aVF is +90°; +60° projects positively on both."),
    kind: "vector_lab",
    initialAngleDeg: -90,
    targetAngleDeg: 60,
    toleranceDeg: 12,
    targetLabel: "mean frontal QRS vector near plus sixty degrees",
    predictions: [
      { lead: "I", expected: "positive" },
      { lead: "aVF", expected: "positive" },
    ],
  },
  {
    ...interactionBase("m01-s9-table", "Classify the four coarse I/aVF polarity combinations.", "Use lead II only to refine the I-positive/aVF-negative leftward quadrant.", ["discriminate"], "All four quadrants and the lead-II refinement are correct.", "Most quadrants are correct.", "Reversing toward and away would reverse the axis statement.", "I+/aVF+ usual; I+/aVF− leftward/check II; I−/aVF+ rightward; both negative extreme."),
    kind: "categorize",
    items: [
      { id: "pp", label: "I positive, aVF positive" },
      { id: "pn", label: "I positive, aVF negative" },
      { id: "np", label: "I negative, aVF positive" },
      { id: "nn", label: "I negative, aVF negative" },
    ],
    categories: [
      { id: "usual", label: "Usual quadrant" },
      { id: "left", label: "Leftward; inspect lead II" },
      { id: "right", label: "Rightward quadrant" },
      { id: "extreme", label: "Extreme quadrant" },
    ],
    correctCategoryByItem: { pp: "usual", pn: "left", np: "right", nn: "extreme" },
  },
  {
    ...interactionBase("m01-s9-refine", "Lead I is positive, aVF is negative, and lead II is positive. What is the best coarse statement?", "Use the corrected lead-II boundary.", ["discriminate", "calibrate_confidence"], "Positive lead II places this leftward pattern within the usual adult teaching range down to about −30°.", "You identified the leftward quadrant.", "I+/aVF− is not automatically left-axis deviation; lead II refines the boundary.", "If lead II remains positive, describe the axis as leftward but within the usual coarse teaching range."),
    kind: "single_select",
    options: [
      { id: "border", label: "Leftward, but within the usual coarse teaching range because lead II remains positive.", rationale: "Correct." },
      { id: "lad", label: "Definite left-axis deviation solely because aVF is negative.", rationale: "Lead II refinement matters." },
      { id: "right", label: "Right-axis deviation because lead II is positive.", rationale: "The quadrant is not rightward." },
      { id: "extreme", label: "Extreme axis because one inferior lead is negative.", rationale: "Both I and aVF would be negative." },
    ],
    correctOptionId: "border",
  },
];

const modeledSweepStages = [
  {
    id: "quality",
    heading: "Calibration & quality",
    revealCopy: "Packet A is displayed at 25 mm/s and 10 mm/mV. QRS landmarks are readable; fine P-wave detail is limited in one lead.",
    question: "What should be recorded first?",
    options: [
      { id: "qualified", label: "Record calibration and name which domains are readable.", rationale: "Correct." },
      { id: "normal", label: "Call the ECG normal because calibration is standard.", rationale: "Calibration does not establish morphology." },
      { id: "ignore", label: "Ignore signal quality once a machine report exists.", rationale: "The trace must support each claim." },
    ],
    acceptableOptionIds: ["qualified"],
  },
  {
    id: "rate",
    heading: "Regularity & rate",
    revealCopy: "A continuous six-second teaching strip contains eight visibly variable R–R intervals and eight QRS complexes.",
    question: "Which method and wording fit?",
    options: [
      { id: "average", label: "Count ×10 and report an average ventricular rate near 80/min.", rationale: "Correct." },
      { id: "single", label: "Use one R–R interval and report an exact rate.", rationale: "A single interval misrepresents variability." },
      { id: "median", label: "Estimate regularity from the median tiles.", rationale: "Median tiles lack beat-to-beat timing." },
    ],
    acceptableOptionIds: ["average"],
  },
  {
    id: "source",
    heading: "Atrial source & P–QRS",
    revealCopy: "P waves are upright in II, negative in aVR, repeatable, and each precedes the next QRS with a stable relationship.",
    question: "Which two-part description is supported?",
    options: [
      { id: "sinus-one", label: "Sinus P-wave pattern with one-to-one P–QRS relationship.", rationale: "Correct." },
      { id: "one-only", label: "One-to-one conduction proves sinus source without P morphology.", rationale: "Source and relationship are distinct." },
      { id: "rate-source", label: "The rate alone proves sinus source.", rationale: "Rate does not establish source." },
    ],
    acceptableOptionIds: ["sinus-one"],
  },
  {
    id: "axis",
    heading: "Axis",
    revealCopy: "The full QRS is net positive in lead I and aVF.",
    question: "What coarse axis statement is supported?",
    options: [
      { id: "usual", label: "Mean frontal QRS axis is in the usual quadrant.", rationale: "Correct." },
      { id: "lad", label: "Left-axis deviation.", rationale: "The polarity combination does not support this." },
      { id: "t", label: "Axis is based on T-wave polarity.", rationale: "Use the full QRS." },
    ],
    acceptableOptionIds: ["usual"],
  },
  {
    id: "timing",
    heading: "Timing: PR, QRS, QT span",
    revealCopy: "Reviewed teaching measurements are PR 180 ms and QRS 92 ms. The T-wave end is indistinct in the available lead.",
    question: "Which statement preserves the measurement boundary?",
    options: [
      { id: "bounded", label: "PR is within the usual teaching span, QRS is narrow, and QT is not assessable here.", rationale: "Correct." },
      { id: "all-normal", label: "All intervals are normal, including QT.", rationale: "QT was not measurable." },
      { id: "whole-normal", label: "A narrow QRS makes the whole ECG normal.", rationale: "Narrow describes one domain." },
    ],
    acceptableOptionIds: ["bounded"],
  },
  {
    id: "stt",
    heading: "ST–T",
    revealCopy: "A stable TP reference and J point are visible in lead II; fine ST assessment is limited in V2 by baseline artifact.",
    question: "Which wording is defensible?",
    options: [
      { id: "lead-aware", label: "Describe lead II relative to its TP baseline; mark V2 ST as not assessable.", rationale: "Correct." },
      { id: "global", label: "One readable lead proves there is no ST–T abnormality anywhere.", rationale: "The claim exceeds the available leads." },
      { id: "acute", label: "Artifact in V2 proves acute ischemia.", rationale: "Artifact cannot establish cause." },
    ],
    acceptableOptionIds: ["lead-aware"],
  },
  {
    id: "synthesis",
    heading: "Synthesis",
    revealCopy: "The findings above are all the information available for this practice ECG.",
    question: "How should the final line be constructed?",
    options: [
      { id: "descriptive", label: "Lead with supported descriptive findings and explicitly name unavailable domains.", rationale: "Correct." },
      { id: "diagnosis", label: "Replace the evidence with one unqualified diagnosis.", rationale: "The module stops at supported description." },
      { id: "treatment", label: "Add a treatment recommendation from the tracing alone.", rationale: "Clinical management is outside this evidence." },
    ],
    acceptableOptionIds: ["descriptive"],
    unsafeOptionIds: ["treatment"],
  },
];

// Packet B deliberately differs from the modeled packet. It is the faded
// "we do" example: the learner must preserve a slow rate description, a long
// PR observation, and a leftward-but-still-usual axis boundary without copying
// the answers from S10.
const guidedSweepStages = [
  {
    id: "quality",
    heading: "Calibration & quality",
    revealCopy: "Packet B is displayed at 25 mm/s and 10 mm/mV. The continuous lead-II strip and limb-lead QRS complexes are readable; fine recovery detail in V1 is limited by baseline motion.",
    question: "What is the safest opening statement?",
    options: [
      { id: "bounded", label: "Record standard calibration and name V1 recovery detail as limited while preserving the readable domains.", rationale: "Correct." },
      { id: "discard", label: "Discard the entire ECG because one lead has motion artifact.", rationale: "A local limitation does not erase readable evidence elsewhere." },
      { id: "normal", label: "Call the ECG normal because speed and gain are standard.", rationale: "Calibration does not establish the findings." },
    ],
    acceptableOptionIds: ["bounded"],
  },
  {
    id: "rate",
    heading: "Regularity & rate",
    revealCopy: "R–R intervals are regular. A measured interval is about 1.03 seconds, and six QRS complexes span a little more than six seconds.",
    question: "Which rate statement fits both measurements?",
    options: [
      { id: "slow", label: "Regular ventricular rate near 58/min; report it as a slow-rate description.", rationale: "Correct." },
      { id: "exact", label: "Exactly 60/min, because every six-second count is exact.", rationale: "The strip supports an estimate, not false precision." },
      { id: "irregular", label: "Irregular rhythm because the rate is below 60/min.", rationale: "Rate and regularity are separate observations." },
    ],
    acceptableOptionIds: ["slow"],
  },
  {
    id: "source",
    heading: "Atrial source & P–QRS",
    revealCopy: "P waves repeat with the same shape, are upright in II and negative in aVR, and maintain a one-to-one relationship with the next QRS.",
    question: "Which source and relationship statement is supported?",
    options: [
      { id: "sinus", label: "Sinus P-wave pattern with one-to-one P–QRS relationship; the slow rate does not undo the source evidence.", rationale: "Correct." },
      { id: "not-sinus", label: "The pattern cannot be sinus because the ventricular rate is below 60/min.", rationale: "Rate is not part of the source definition." },
      { id: "conduction-only", label: "One-to-one conduction proves sinus source without considering P-wave direction or shape.", rationale: "Source and relationship require separate evidence." },
    ],
    acceptableOptionIds: ["sinus"],
  },
  {
    id: "axis",
    heading: "Axis",
    revealCopy: "The full QRS is net positive in lead I, net negative in aVF, and remains net positive in lead II.",
    question: "How should the coarse axis be reported?",
    options: [
      { id: "border", label: "Leftward, but within the usual coarse teaching range because lead II remains positive.", rationale: "Correct." },
      { id: "lad", label: "Definite left-axis deviation solely because aVF is negative.", rationale: "Lead II refines this border." },
      { id: "right", label: "Right-axis deviation because one inferior lead is positive.", rationale: "Lead I and aVF establish the quadrant first." },
    ],
    acceptableOptionIds: ["border"],
  },
  {
    id: "timing",
    heading: "Timing: PR, QRS, QT span",
    revealCopy: "Reviewed boundaries give PR 220 ms, QRS 108 ms, and a visible QT span of about 410 ms. Rate correction is not part of this lesson.",
    question: "Which finding-language statement stays within scope?",
    options: [
      { id: "measured", label: "PR is long, QRS is narrow, and the measured QT span is about 410 ms without making a QTc claim.", rationale: "Correct." },
      { id: "block", label: "The long PR alone proves a named AV block diagnosis.", rationale: "Foundations reports the observation before a mechanism label." },
      { id: "all-normal", label: "All timing is normal because QRS is under 120 ms.", rationale: "The PR measurement is long and domains remain separate." },
    ],
    acceptableOptionIds: ["measured"],
  },
  {
    id: "stt",
    heading: "ST–T",
    revealCopy: "In II and V5, the TP baseline and J point are stable, ST lies near baseline, and T is upright. V1 remains limited by baseline motion.",
    question: "Which description preserves the lead boundary?",
    options: [
      { id: "lead-aware", label: "Describe the visible II/V5 recovery pattern and state that fine V1 recovery detail is limited.", rationale: "Correct." },
      { id: "global", label: "Declare all twelve leads normal from II and V5 alone.", rationale: "The conclusion exceeds the reviewed leads." },
      { id: "cause", label: "Assign a disease cause to the V1 artifact.", rationale: "Artifact is a signal limit, not a diagnosis." },
    ],
    acceptableOptionIds: ["lead-aware"],
  },
  {
    id: "synthesis",
    heading: "Synthesis",
    revealCopy: "Packet B supports a regular slow sinus-pattern read, a long PR observation, a narrow QRS, a leftward-but-usual coarse axis, and a lead-specific V1 limitation.",
    question: "Which synthesis strategy is strongest?",
    options: [
      { id: "descriptive", label: "Combine the supported findings in one line and keep the V1 limitation beside the recovery statement it constrains.", rationale: "Correct." },
      { id: "copy", label: "Reuse Packet A’s summary because both examples belong to Foundations.", rationale: "Each ECG needs its own evidence-linked read." },
      { id: "diagnosis", label: "Replace the measured findings with one unqualified diagnostic label.", rationale: "The evidence supports a descriptive read here." },
    ],
    acceptableOptionIds: ["descriptive"],
  },
];

// Packet C is not a copy of either worked example. It is the first immediate
// integration case and deliberately includes unavailable atrial evidence, a
// wide QRS, and a lead-II axis boundary that requires a different conclusion.
const integrationCaseOneStages = [
  {
    id: "quality",
    heading: "Calibration & quality",
    revealCopy: "Packet C is displayed at 25 mm/s and 10 mm/mV. QRS timing and limb-lead polarity are readable. Low-amplitude atrial detail is obscured in both II and aVR.",
    question: "What should the quality statement preserve?",
    options: [
      { id: "domain", label: "Preserve QRS timing and axis evidence; mark atrial-source assessment as limited.", rationale: "Correct." },
      { id: "whole", label: "The entire ECG is uninterpretable because P waves are unclear.", rationale: "Several domains remain readable." },
      { id: "negative", label: "No visible P wave proves that no atrial activity is present.", rationale: "Unavailable evidence is not negative evidence." },
    ],
    acceptableOptionIds: ["domain"],
  },
  {
    id: "rate",
    heading: "Regularity & rate",
    revealCopy: "Consecutive R waves are separated by about four large boxes throughout a continuous strip at 25 mm/s.",
    question: "Which rate statement follows?",
    options: [
      { id: "regular-75", label: "Regular ventricular rate near 75/min using 300 ÷ 4.", rationale: "Correct." },
      { id: "irregular", label: "Use a six-second irregular average because P waves are unclear.", rationale: "P-wave visibility does not determine R–R regularity." },
      { id: "exact", label: "Exactly 75/min with no measurement uncertainty.", rationale: "The box method is an estimate." },
    ],
    acceptableOptionIds: ["regular-75"],
  },
  {
    id: "source",
    heading: "Atrial source & P–QRS",
    revealCopy: "The representation does not show repeatable P-wave onset, shape, or direction reliably enough to test source or a P-to-next-QRS relationship.",
    question: "Which conclusion is defensible?",
    options: [
      { id: "na", label: "Atrial source and P–QRS relationship are not assessable in this representation.", rationale: "Correct." },
      { id: "af", label: "The rhythm is atrial fibrillation because P waves are not visible.", rationale: "Poor P-wave visibility alone cannot establish that diagnosis." },
      { id: "sinus", label: "The rhythm is sinus because the ventricular intervals are regular.", rationale: "Regularity does not establish atrial source." },
    ],
    acceptableOptionIds: ["na"],
  },
  {
    id: "axis",
    heading: "Axis",
    revealCopy: "The full QRS is positive in lead I and negative in both aVF and lead II.",
    question: "What coarse axis statement is supported?",
    options: [
      { id: "left", label: "Left-axis deviation by the I/aVF quadrant with negative lead-II refinement.", rationale: "Correct." },
      { id: "usual", label: "Usual axis because lead I is positive.", rationale: "aVF and lead II change the conclusion." },
      { id: "right", label: "Right-axis deviation because the inferior leads are negative.", rationale: "Right-axis deviation has negative I with positive aVF." },
    ],
    acceptableOptionIds: ["left"],
  },
  {
    id: "timing",
    heading: "Timing: PR, QRS, QT span",
    revealCopy: "PR cannot be measured because P onset is unavailable. QRS onset-to-final-offset is 136 ms. The T-wave end supports a QT span measurement, but correction is deferred.",
    question: "Which wording respects all three boundaries?",
    options: [
      { id: "bounded", label: "PR not assessable; QRS wide at 136 ms; report the measured QT span without a QTc category here.", rationale: "Correct." },
      { id: "normal", label: "All intervals are normal because the ventricular rate is near 75/min.", rationale: "Rate does not erase the unavailable PR or wide QRS." },
      { id: "block", label: "The wide QRS alone proves a specific bundle-branch diagnosis.", rationale: "A named cause requires morphology taught later." },
    ],
    acceptableOptionIds: ["bounded"],
  },
  {
    id: "stt",
    heading: "ST–T",
    revealCopy: "The TP baseline is stable in II and V5, where ST lies near baseline. Baseline wander prevents fine ST comparison in V2.",
    question: "Which recovery statement is supported?",
    options: [
      { id: "bounded", label: "Describe II and V5 relative to their baseline and mark fine V2 ST assessment as limited.", rationale: "Correct." },
      { id: "global", label: "There is no ST–T abnormality anywhere because II is near baseline.", rationale: "One lead cannot clear every lead." },
      { id: "acute", label: "V2 baseline wander proves acute injury.", rationale: "Artifact does not establish a pathologic cause." },
    ],
    acceptableOptionIds: ["bounded"],
  },
  {
    id: "synthesis",
    heading: "Synthesis",
    revealCopy: "Packet C supports a regular ventricular rate near 75/min, unavailable atrial-source evidence, left-axis deviation, a wide QRS, and lead-specific recovery limits.",
    question: "How should the final line be built?",
    options: [
      { id: "bounded", label: "State the supported measurements and directions, then keep unavailable atrial and V2 recovery evidence explicit.", rationale: "Correct." },
      { id: "normal", label: "Call the ECG normal because the rate is in the usual range.", rationale: "Multiple domains conflict with that claim." },
      { id: "treat", label: "Recommend treatment from the wide QRS alone.", rationale: "Management needs diagnosis and clinical context beyond this exercise." },
    ],
    acceptableOptionIds: ["bounded"],
    unsafeOptionIds: ["treat"],
  },
];

const s10: LearningInteraction[] = [
  {
    ...interactionBase("m01-s10-modeled", "Predict each step before the example interpretation appears.", "Answer one part at a time before seeing the example wording.", ["synthesize", "calibrate_confidence"], "All seven predictions follow the ECG findings and their limits.", "Several predictions follow the sequence.", "The complete read must start with signal quality and end with a concise summary.", "Work one part at a time; use not assessable when the ECG does not show enough."),
    kind: "clinical_stage",
    stages: modeledSweepStages,
  },
  {
    ...interactionBase("m01-s10-order", "Reconstruct the formal sweep without prompts.", "Order all seven cards exactly.", ["synthesize"], "The complete sweep is available for retrieval.", "Most of the rail is in sequence.", "Dependencies are out of order.", "Calibration/quality first; synthesis last."),
    kind: "sequence",
    cards: M01_FORMAL_SWEEP.map((label, index) => ({ id: `sweep-${index + 1}`, label })),
    correctOrder: M01_FORMAL_SWEEP.map((_, index) => `sweep-${index + 1}`),
  },
  {
    ...interactionBase("m01-s10-ceiling", "Sort each statement by whether the practice ECG supports it.", "Use only the findings revealed after your predictions.", ["discriminate", "calibrate_confidence"], "Supported observations, unavailable findings, and overclaims are separated.", "Most statements are in the right group.", "One normal-appearing feature does not justify calling the whole ECG normal or recommending treatment.", "Connect each conclusion to a visible finding; otherwise choose unavailable or overclaim."),
    kind: "categorize",
    items: [
      { id: "qrs", label: "QRS is narrow at the measured 92 ms" },
      { id: "qt", label: "QT is not assessable because T-wave end is indistinct" },
      { id: "normal", label: "The patient is completely normal" },
      { id: "treatment", label: "No further clinical evaluation is needed" },
    ],
    categories: [
      { id: "supported", label: "Supported descriptive claim" },
      { id: "unavailable", label: "Supported not-assessable statement" },
      { id: "overclaim", label: "Unsupported overclaim" },
    ],
    correctCategoryByItem: { qrs: "supported", qt: "unavailable", normal: "overclaim", treatment: "overclaim" },
  },
];

const foundationsCapstoneForbiddenClaims = [
  {
    id: "diagnosis",
    label: "Unsupported diagnostic label",
    terms: ["diagnosis", "diagnostic of", "normal ECG", "normal tracing", "tracing is normal", "ECG is normal", "overall normal", "STEMI", "NSTEMI", "infarct", "ischemia", "ischemic", "arrhythmia", "atrial fibrillation", "atrial flutter", "bundle branch block", "heart block", "hypertrophy", "strain pattern", "pericarditis", "pre-excitation", "Wellens", "WPW"],
    misconception: "unsupported_diagnosis_urgency_or_treatment",
  },
  {
    id: "urgency",
    label: "Unsupported urgency claim",
    terms: ["urgent", "emergency", "unstable", "activate", "cath lab", "code blue", "STEMI activation"],
    misconception: "unsupported_diagnosis_urgency_or_treatment",
  },
  {
    id: "treatment",
    label: "Unsupported treatment recommendation",
    terms: ["treat", "treatment", "administer", "prescribe", "heparin", "aspirin", "anticoagulation", "adenosine", "amiodarone", "atropine", "nitroglycerin", "beta blocker", "calcium channel blocker", "medication", "cardioversion", "defibrillation", "pacing", "revascularization"],
    misconception: "unsupported_diagnosis_urgency_or_treatment",
  },
];

const s11: LearningInteraction[] = [
  {
    ...interactionBase("m01-s11-faded-sweep", "Complete the seven-step read with less guidance.", "One part opens at a time. Answer before the next detail appears; earlier answers remain visible.", ["synthesize", "apply_in_context"], "Every part is answered with a visible finding or a valid not-assessable choice.", "Several parts are already well supported.", "A complete read cannot skip a part or assume that missing information is normal.", "Return to the first unsupported part and make the smallest needed change.", 2),
    kind: "clinical_stage",
    stages: guidedSweepStages.map((stage, index) => ({
      ...stage,
      id: `faded-${stage.id}`,
      revealCopy: index < 3 ? stage.revealCopy : `Support is fading. ${stage.revealCopy}`,
    })),
  },
  {
    ...interactionBase("m01-s11-evidence-notebook", "Match each conclusion to the finding that supports it.", "Use only the visible lead, waveform, or measurement. There is no hidden diagnosis.", ["synthesize", "calibrate_confidence"], "Each conclusion points to the correct ECG finding.", "Most links are correct.", "A conclusion linked to the wrong lead, wave, or interval can change the interpretation.", "Rate needs QRS timing; source needs P-wave shape; axis needs limb-lead QRS direction; intervals need clear endpoints."),
    kind: "pairing",
    left: [
      { id: "rate", label: "Average ventricular rate near 80/min" },
      { id: "source", label: "Sinus P-wave pattern" },
      { id: "axis", label: "Usual coarse frontal quadrant" },
      { id: "qrs", label: "QRS narrow at 92 ms" },
      { id: "qt-na", label: "QT not assessable" },
    ],
    right: [
      { id: "six", label: "Six-second QRS count" },
      { id: "p", label: "P direction in II/aVR" },
      { id: "iaVF", label: "Full-QRS polarity in I/aVF" },
      { id: "boundaries", label: "QRS onset and final offset" },
      { id: "t-end", label: "Indistinct T-wave end" },
    ],
    correctPairs: { rate: "six", source: "p", axis: "iaVF", qrs: "boundaries", "qt-na": "t-end" },
  },
  {
    ...interactionBase("m01-s11-synthesis", "Write a concise evidence-limited synthesis.", "Include rate/rhythm evidence, axis, timing, ST–T limits, and one explicit uncertainty. Do not add a diagnosis, urgency, or treatment.", ["synthesize", "calibrate_confidence"], "Your synthesis communicates the supported domains and their limits.", "Several required domains are present.", "A complete read needs both supported findings and explicit boundaries.", "Use one clause each for rate/rhythm, axis, intervals/QRS, ST–T, and uncertainty."),
    kind: "free_response",
    responseLabel: "Descriptive synthesis",
    placeholder: "Calibration/quality … Rate/rhythm … Axis … PR/QRS/QT … ST–T … Overall limitation …",
    minimumCharacters: 90,
    sentenceFrame: "Supported finding + evidence; unavailable domain + reason; no diagnosis or management",
    forbiddenClaims: foundationsCapstoneForbiddenClaims,
    rubric: [
      { id: "rate", label: "Rate or regularity", acceptedConcepts: ["rate", "bpm", "regular", "irregular", "ventricular"], required: true, misconceptionIfMissing: "rate_domain_missing" },
      { id: "axis", label: "Axis", acceptedConcepts: ["axis", "frontal quadrant"], required: true, misconceptionIfMissing: "axis_domain_missing" },
      { id: "timing", label: "PR/QRS/QT", acceptedConcepts: ["PR", "QRS", "QT", "interval"], required: true, misconceptionIfMissing: "timing_domain_missing" },
      { id: "stt", label: "ST–T", acceptedConcepts: ["ST", "T wave", "repolarization"], required: true, misconceptionIfMissing: "recovery_domain_missing" },
      { id: "uncertainty", label: "Explicit uncertainty", acceptedConcepts: ["not assessable", "limited", "uncertain", "cannot assess"], required: true, misconceptionIfMissing: "uncertainty_missing" },
      { id: "scope", label: "Clinical scope boundary", acceptedConcepts: ["cannot diagnose", "no diagnosis", "clinical context", "cannot recommend treatment", "no treatment recommendation", "management cannot be determined"], required: true, misconceptionIfMissing: "clinical_scope_boundary_missing" },
    ],
  },
];

const s12: LearningInteraction[] = [
  {
    ...interactionBase("m01-s12-case-one", "ECG 1: complete the full seven-step read.", "Work through the ECG from signal quality to your final summary. Answer every part or mark it not assessable.", ["synthesize", "apply_in_context"], "All seven parts are addressed without adding a claim the tracing cannot support.", "Several parts are already well supported.", "A complete read cannot treat missing information as normal or skip signal quality.", "Revise the first part that does not name a visible finding.", 2),
    kind: "clinical_stage",
    stages: integrationCaseOneStages.map((stage) => ({ ...stage, id: `case-one-${stage.id}`, heading: `Case 1 · ${stage.heading}` })),
  },
  {
    ...interactionBase("m01-s12-case-two", "ECG 2: match each conclusion to what supports it.", "Choose the relevant ECG finding for each conclusion, then write your final interpretation in the next question.", ["synthesize", "calibrate_confidence"], "Every conclusion is linked to the right ECG finding.", "Most links are correct.", "A conclusion linked to the wrong finding can change the interpretation.", "Use waveform timing for rate, P waves for source, limb-lead QRS direction for axis, and clear endpoints for intervals."),
    kind: "categorize",
    items: [
      { id: "variable", label: "Ventricular intervals vary across the continuous strip" },
      { id: "source", label: "Repeatable P waves are upright in II, negative in aVR, and precede each QRS" },
      { id: "usual", label: "Full QRS is net positive in both I and aVF" },
      { id: "narrow", label: "QRS measures 96 ms from onset to final offset" },
      { id: "qt-na", label: "QT is not assessable because the T-wave endpoint is merged with artifact" },
    ],
    categories: [
      { id: "timing", label: "Continuous QRS timing" },
      { id: "p", label: "P-wave visibility/direction" },
      { id: "limb", label: "Full-QRS limb-lead polarity" },
      { id: "interval", label: "QRS onset-to-offset measurement" },
      { id: "t-end", label: "T-wave endpoint visibility" },
    ],
    correctCategoryByItem: { variable: "timing", source: "p", usual: "limb", narrow: "interval", "qt-na": "t-end" },
  },
  {
    ...interactionBase("m01-s12-final-synthesis", "Write the final descriptive read for Case 2.", "Use all seven sweep domains. Every positive clause must be traceable to the evidence categories you just linked; name any unavailable domain.", ["synthesize", "calibrate_confidence"], "Your final line is organized, evidence-limited, and explicit about uncertainty.", "Several clauses are usable and can be preserved.", "The final line is incomplete or contains a claim that outruns its evidence.", "Keep valid clauses. Change only the first unsupported clause, then reread the seven-domain rail."),
    kind: "free_response",
    responseLabel: "Final descriptive ECG read",
    placeholder: "Calibration/quality … Regularity/rate … Atrial source/P–QRS … Axis … PR/QRS/QT … ST–T … Synthesis …",
    minimumCharacters: 120,
    sentenceFrame: "Observation → evidence → bounded conclusion → uncertainty",
    forbiddenClaims: foundationsCapstoneForbiddenClaims,
    rubric: [
      { id: "quality", label: "Calibration/quality", acceptedConcepts: ["calibration", "quality", "readable", "artifact"], required: true, misconceptionIfMissing: "quality_missing" },
      { id: "rate-source", label: "Rate and atrial source", acceptedConcepts: ["rate", "ventricular", "atrial source", "P wave", "not assessable"], required: true, misconceptionIfMissing: "rate_source_missing" },
      { id: "axis", label: "Axis", acceptedConcepts: ["axis", "leftward", "rightward", "usual quadrant"], required: true, misconceptionIfMissing: "axis_missing" },
      { id: "timing", label: "PR/QRS/QT", acceptedConcepts: ["PR", "QRS", "QT", "interval"], required: true, misconceptionIfMissing: "timing_missing" },
      { id: "stt", label: "ST–T", acceptedConcepts: ["ST", "T wave", "recovery", "baseline"], required: true, misconceptionIfMissing: "stt_missing" },
      { id: "limits", label: "Claim boundary", acceptedConcepts: ["not assessable", "limited", "uncertain", "cannot determine"], required: true, misconceptionIfMissing: "claim_boundary_missing" },
      { id: "scope", label: "Clinical scope boundary", acceptedConcepts: ["cannot diagnose", "no diagnosis", "clinical context", "cannot recommend treatment", "no treatment recommendation", "management cannot be determined"], required: true, misconceptionIfMissing: "clinical_scope_boundary_missing" },
    ],
  },
  {
    ...interactionBase("m01-s12-confidence", "How should confidence be communicated after this complete read?", "Choose the confidence statement that follows evidence availability rather than familiarity.", ["calibrate_confidence"], "Confidence is attached to domains and evidence limits, not to a global feeling.", "You recognized that uncertainty belongs in the final communication.", "A confident global label cannot erase unavailable domains.", "State high confidence only for supported domains and lower confidence where representation or landmarks limit the claim."),
    kind: "single_select",
    options: [
      { id: "domain", label: "High confidence in the measured domains; limited confidence where P waves or ST baseline are not assessable.", rationale: "Correct." },
      { id: "global-high", label: "High confidence in the entire ECG because every field was completed.", rationale: "Completion does not create missing evidence." },
      { id: "none", label: "Never communicate confidence or uncertainty in an ECG read.", rationale: "Calibrated uncertainty is part of communication." },
      { id: "machine", label: "Confidence should equal the machine report confidence.", rationale: "The learner must ground their own claim." },
    ],
    correctOptionId: "domain",
  },
];

const twelveLeadContrast = (lessonId: string, requestedConcept: string, leads: string[], casePoolSlot: string) => caseContract({
  selectorLessonId: lessonId,
  requestedConcept,
  minimumTier: "B",
  requiredEvidence: ["representation metadata", "guided comparison only"],
  requiredLeads: leads,
  allowedUses: ["mechanism", "worked_example"],
  fallback: "contrast_only",
  forbiddenClaims: [
    "Beat-to-beat rhythm from median morphology tiles",
    "Independent landmark or interval credit without reviewed geometry",
    "Diagnosis, urgency, or treatment from the tutorial representation",
  ],
  casePoolSlot,
});

const integratedContrast = (casePoolSlot: string) => caseContract({
  selectorLessonId: "integrated-interpretation",
  requestedConcept: "normal_ecg",
  minimumTier: "A",
  requiredEvidence: ["roi:reviewed_complete_sweep_manifest"],
  requiredLeads: ["I", "II", "aVF", "aVR", "V1", "V2", "V3", "V4", "V5", "V6"],
  allowedUses: ["worked_example"],
  fallback: "contrast_only",
  forbiddenClaims: [
    "Independent whole-ECG score from client phrase matching",
    "Missing domain defaulted to normal",
    "Clinical diagnosis, urgency, or treatment",
  ],
  casePoolSlot,
  retryCasePoolSlot: "foundations:equivalent-retry",
});

export const M01_FOUNDATIONS_MODULE: ProductionModule = {
  id: "foundations",
  order: 1,
  title: "Foundations of ECG Interpretation",
  shortTitle: "Foundations",
  duration: "About 2 hours across four resumable chapters",
  outcome: "Build a clear, repeatable ECG read from calibration and signal quality through rate, atrial source, axis, intervals, ST–T, and a final summary.",
  prerequisiteIds: [],
  accent: "#2458d6",
  sourceRequirementIds: ["SPEC-11.1", "SPEC-11.3", "SPEC-11.5", "SPEC-11.16"],
  scenes: [
    buildScene({
      id: "S0", partId: "Chapter 1 · Signal before labels", minutes: 5, title: "A reliable ECG read, every time", objective: "Seven checkpoints keep you from missing the signal before naming the pattern.",
      setup: ["An ECG is a story told in order. Start with the recording, move through the waveform, and synthesize only after the evidence is clear."],
      mechanism: ["Signal quality and calibration affect every later conclusion.", "The same seven steps work for both simple and complex ECGs.", "You will first practise with guidance, then apply the process more independently."],
      clinicalHeading: "Describe before you diagnose", clinicalBody: "Urgency, treatment, and patient-specific decisions also require the clinical story and supervised judgment.", transition: "Build the seven-step route, then choose the principles that keep an interpretation safe and useful.", completionBody: "Your reading roadmap is ready. Next, you’ll begin with the waveform itself.", requirements: ["SPEC-11.1", "SPEC-11.16"], interactions: s0,
      connections: { recallFrom: "No prior ECG knowledge is required", changesNow: "A stable evidence-first route replaces guessing", reuseNext: "Every scene and every later mode", clinicalUse: "Prevents interpretation from outrunning signal quality" },
      handoffs: [handoff("train", "Focused · Preview the complete sweep", "foundations_systematic_sweep", "synthesize", "guided", { focus: "integrated_interpretation", subskill: "synthesize" })], tutorPrompt: "Which step protects all the later steps from an invalid ruler or unreadable signal?", hints: ["Acquisition comes before interpretation.", "The final step should combine—not replace—the earlier evidence."], independent: false,
    }),
    buildScene({
      id: "S1", partId: "Chapter 1 · Signal before labels", minutes: 8, title: "One beat, one electrical story", objective: "Locate P, QRS, and T and connect each to electrical activation or recovery.", setup: ["Waveform names become useful only when they remain attached to the event and location they describe."], mechanism: ["Atrial activation contributes to P.", "Rapid ventricular activation produces QRS.", "Ventricular recovery contributes to T; none of these directly measures contraction strength."], clinicalHeading: "Electrical is not mechanical", clinicalBody: "A tracing can suggest electrical organization without directly measuring perfusion, pressure, or contraction.", transition: "Explore the model, then mark all three landmarks on a different beat.", completionBody: "You can find the three principal waveform components and explain the electrical story they encode.", requirements: ["SPEC-11.1"], interactions: s1,
      connections: { recallFrom: "S0 evidence-first scope", changesNow: "A whole beat is separated into electrical events", reuseNext: "Intervals, rhythm, conduction, and recovery", clinicalUse: "Keeps waveform labels grounded in physiology" },
      handoffs: [handoff("train", "Focused · Waveform landmarks", "foundations_waveform_landmarks", "localize", "guided", { focus: "waveform_components", subskill: "localize" })], tutorPrompt: "What electrical event changes between the P wave, QRS complex, and T wave?", hints: ["Use order before shape.", "The ECG records voltage projection, not pressure."],
    }),
    buildScene({
      id: "S2", partId: "Chapter 1 · Signal before labels", minutes: 10, title: "The grid is your ruler", objective: "Read calibration, convert boxes into time and voltage, and change the calculation when paper speed changes.", setup: ["A number is meaningful only when its ruler, endpoints, and units are valid."], mechanism: ["At 25 mm/s, one small horizontal box is 40 ms and one large box is 200 ms.", "At 10 mm/mV, 10 vertical millimeters represent 1 mV.", "At 50 mm/s, each horizontal box represents half as much time."], clinicalHeading: "Calibration errors propagate", clinicalBody: "A wrong speed or gain can change every downstream rate, interval, and voltage claim.", transition: "Pair the ruler values, place a real span, then transfer to faster paper.", completionBody: "You can establish the ruler before using a measurement.", requirements: ["SPEC-11.1"], interactions: s2,
      connections: { recallFrom: "S1 waveform boundaries", changesNow: "Visual spans become measurements with units", reuseNext: "Rate, PR, QRS, QT, and voltage", clinicalUse: "Prevents confident calculations from invalid calibration" },
      handoffs: [handoff("train", "Focused · ECG grid and calibration", "foundations_calibration", "measure", "guided", { focus: "ecg_grid_calibration", subskill: "measure" })], tutorPrompt: "What must you verify before converting a box count into milliseconds or millivolts?", hints: ["Read speed and gain from the trace.", "Keep horizontal time separate from vertical voltage."],
    }),
    buildScene({
      id: "S3", partId: "Chapter 1 · Signal before labels", minutes: 9, title: "Readable for what?", objective: "Judge which parts of an ECG are readable, locate artifact, and use not assessable without discarding valid findings.", setup: ["Quality is not one global yes/no label. A strip may support QRS timing while obscuring P waves or fine ST–T detail."], mechanism: ["Name the question before judging readability.", "Locate what limits that question.", "Keep the findings you can trust and clearly mark what is unavailable."], clinicalHeading: "Not assessable is a useful conclusion", clinicalBody: "Saying what cannot be assessed is safer and more informative than guessing or discarding the entire tracing.", transition: "Judge each part, box the limiting interval, then choose the strongest conclusion the tracing supports.", completionBody: "You can keep usable findings while withholding conclusions the signal cannot support.", requirements: ["SPEC-11.1", "SPEC-16.paced_or_artifact_mistaken_for_arrhythmia"], interactions: s3,
      connections: { recallFrom: "S2 calibration", changesNow: "Readability is tied to a specific claim", reuseNext: "Rate, source, intervals, ST–T, and cases", clinicalUse: "Prevents artifact from becoming a false rhythm or ischemia label" },
      handoffs: [handoff("train", "Focused · Signal quality", "foundations_signal_quality", "discriminate", "guided", { focus: "artifact", subskill: "discriminate" })], tutorPrompt: "Which domain remains observable even when atrial activity or the baseline is obscured?", hints: ["Assess QRS timing, P waves, intervals, and ST–T separately.", "Preserve valid work outside the artifact box."],
    }),
    buildScene({
      id: "S4", partId: "Chapter 2 · Timing and source", minutes: 12, title: "Regular first, then rate", objective: "Mark valid ventricular events, choose a method from regularity, and execute both regular and irregular rate estimates.", setup: ["Method follows regularity. A single R–R interval describes one cycle; a six-second count estimates an average across variable cycles."], mechanism: ["Mark QRS complexes before calculating.", "Use interval geometry for a regular strip.", "Use a true six-second window for an irregular average; never tile a shorter strip."], clinicalHeading: "Rate is a measurement, not a rhythm diagnosis", clinicalBody: "A fast or slow ventricular rate does not by itself identify atrial source or mechanism.", transition: "Anchor QRS events, choose the compatible method, then transfer to an irregular strip.", completionBody: "You can choose and execute a rate method without confusing T waves, median tiles, or short strips with valid timing evidence.", requirements: ["SPEC-11.3"], interactions: s4,
      connections: { recallFrom: "S1 QRS localization, S2 time scale, S3 readability", changesNow: "Regularity selects the rate method", reuseNext: "Atrial source, bradycardia, tachycardia, and serial comparison", clinicalUse: "Produces an auditable ventricular-rate estimate" },
      handoffs: [handoff("rapid", "Rapid · Rate recognition", "foundations_rate", "measure", "faded", { focus: "rate", receiptConcept: "rate", subskill: "measure", pace: "untimed", suggestedLength: 5 }), handoff("train", "Focused · Rate methods", "foundations_rate", "measure", "guided", { focus: "rate", subskill: "measure" })], tutorPrompt: "What did the R–R pattern tell you about the method before you calculated?", hints: ["Mark ventricular events first.", "Use a six-second count only on an actual six-second continuous strip."],
    }),
    buildScene({
      id: "S5", partId: "Chapter 2 · Timing and source", minutes: 10, title: "Is there a sinus P-wave pattern?", objective: "Separate atrial source from the P–QRS relationship and communicate a two-part conclusion.", setup: ["Atrial source and conduction relationship answer different questions. One-to-one P–QRS conduction does not prove where the atrial impulse began."], mechanism: ["Find repeatable P waves.", "Use lead-II and aligned aVR direction when available.", "Then assess chronological P-to-next-QRS relationships separately."], clinicalHeading: "Rate does not name the source", clinicalBody: "A regular rate may coexist with several atrial sources; unavailable P waves require an unavailable source statement.", transition: "Mark the events, sort the findings, then make a careful two-part conclusion.", completionBody: "You can report atrial-source findings and the P–QRS relationship without mixing them together.", requirements: ["SPEC-11.4", "SPEC-7.sinus_rhythm"], interactions: s5, caseContract: twelveLeadContrast("rhythm-basics", "sinus_rhythm", ["II", "aVR"], "foundations:S5:component"),
      connections: { recallFrom: "S1 P/QRS landmarks, S3 quality, S4 rate", changesNow: "Source and conduction relationship become separate outputs", reuseNext: "PR, rhythm logic, AV block, and tachyarrhythmias", clinicalUse: "Prevents regular-equals-sinus and absent-equals-AF shortcuts" },
      handoffs: [handoff("train", "Focused · Sinus evidence", "foundations_atrial_source", "discriminate", "guided", { focus: "sinus_rhythm", subskill: "discriminate" }), handoff("rapid", "Rapid · P-wave source clues", "foundations_atrial_source", "recognize", "faded", { focus: "sinus_rhythm", receiptConcept: "sinus_rhythm", subskill: "recognize", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "Which observation speaks to atrial source, and which speaks only to conduction relationship?", hints: ["P morphology and direction address source.", "Chronological P-to-next-QRS links address relationship."],
    }),
    buildScene({
      id: "S6", partId: "Chapter 2 · Timing and source", minutes: 12, title: "Measure PR and QRS", objective: "Place interval boundaries, report values with units, and keep duration categories separate from later diagnoses.", setup: ["PR runs from P onset to QRS onset. QRS duration runs from the first departure to the final return, including terminal forces."], mechanism: ["Clear endpoints come before arithmetic.", "Measure and interpret PR and QRS separately.", "Long PR and wide QRS are observations; specific block labels require later waveform or sequence findings."], clinicalHeading: "Narrow is not otherwise normal", clinicalBody: "A narrow QRS tells you about ventricular activation duration, not whether the rest of the ECG is normal.", transition: "Measure both intervals, then choose wording that does not add a diagnosis prematurely.", completionBody: "You can report reproducible PR and QRS measurements without skipping endpoints or overnaming the finding.", requirements: ["SPEC-11.5", "SPEC-11.7"], interactions: s6, caseContract: twelveLeadContrast("pr-av-block", "pr_interval", ["II", "V1"], "foundations:S6:component"),
      connections: { recallFrom: "S1 landmarks, S2 grid, S5 P–QRS", changesNow: "Timing claims acquire explicit endpoints and units", reuseNext: "M4 AV conduction, M5 ventricular conduction, and M6 width-first rhythm logic", clinicalUse: "Prevents peak-to-peak and width-equals-diagnosis errors" },
      handoffs: [handoff("train", "Focused · PR interval", "foundations_pr_qrs", "measure", "guided", { focus: "pr_interval", subskill: "measure" }), handoff("rapid", "Rapid · QRS width", "foundations_pr_qrs", "discriminate", "faded", { focus: "qrs_duration", receiptConcept: "qrs_duration", subskill: "discriminate", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "Which exact onset and offset define the interval you are measuring?", hints: ["PR ends at QRS onset, not R peak.", "QRS ends after the terminal deflection returns to baseline."],
    }),
    buildScene({
      id: "S7", partId: "Chapter 2 · Timing and source", minutes: 12, title: "Baseline, J point, ST, T, and QT", objective: "Anchor recovery findings to a named baseline, locate J and T, and measure a defensible QT span.", setup: ["Recovery conclusions require a readable baseline, the end of QRS, a named lead, and a visible T wave."], mechanism: ["The J point marks the QRS-to-ST boundary.", "ST direction is judged relative to a stable reference in the same lead.", "QT begins at QRS onset and ends at T-wave end; when that end is unreadable, QT is not assessable."], clinicalHeading: "Description before cause", clinicalBody: "Here, describe location, direction, shape, and limits. Later modules connect those findings to causes and QT correction.", transition: "Mark the landmarks and QT span, then describe activation and recovery in order.", completionBody: "You can describe recovery without using a universal T-wave shortcut or inventing a cause.", requirements: ["SPEC-11.11", "SPEC-11.15"], interactions: s7, caseContract: twelveLeadContrast("qt-qtc", "qt_interval", ["II", "V1", "V5"], "foundations:S7:component"),
      connections: { recallFrom: "S2 grid and S6 QRS boundaries", changesNow: "Recovery statements gain baseline, lead, and endpoint evidence", reuseNext: "M8 repolarization/QT and M9 ischemia", clinicalUse: "Prevents ST–T and QT overcalls from unreadable boundaries" },
      handoffs: [handoff("train", "Focused · QT landmarks", "foundations_recovery", "localize", "guided", { focus: "qt_interval", subskill: "localize" }), handoff("rapid", "Rapid · ST–T description", "foundations_recovery", "recognize", "faded", { focus: "st_t_morphology", receiptConcept: "st_t_morphology", subskill: "recognize", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "Which named baseline and endpoint make your recovery claim reproducible?", hints: ["Find the end of QRS before judging ST.", "QT ends at T-wave end, not at the peak."],
    }),
    buildScene({
      id: "S8", partId: "Chapter 3 · Twelve views and direction", minutes: 11, title: "One event, twelve directed views", objective: "Navigate the 12-lead layout, distinguish shape displays from continuous timing, and explain why the same event looks different across leads.", setup: ["A standard display combines directed views of one evolving electrical process. Printed lead labels and the display format matter."], mechanism: ["Limb leads view the frontal plane; V1–V6 traverse the horizontal chest plane.", "Median waveform panels support shape comparison, not beat-to-beat rhythm timing.", "Compare individual QRS complexes from V1 through V6 before naming the transition point."], clinicalHeading: "Viewpoint changes the waveform", clinicalBody: "A small or negative deflection may reflect geometry rather than a weak or absent cardiac event.", transition: "Locate anchor leads, decide what the display can show, compare the chest leads, then explain the shared event.", completionBody: "You can navigate the display and keep shape conclusions separate from timing conclusions.", requirements: ["SPEC-11.1", "SPEC-11.2", "SPEC-11.9"], interactions: s8, caseContract: twelveLeadContrast("lead-territories", "normal_ecg", ["II", "aVR", "V1", "V3", "V6"], "foundations:S8:component"),
      connections: { recallFrom: "S1 waveform events and S7 recovery", changesNow: "One signal becomes multiple directed projections", reuseNext: "M2 vectors/axis, M7 progression, M9 territories", clinicalUse: "Prevents rhythm inference from median panels and lead misidentification" },
      handoffs: [handoff("train", "Focused · 12-lead navigation", "foundations_twelve_lead_navigation", "localize", "guided", { focus: "normal_ecg", subskill: "localize" }), handoff("rapid", "Rapid · Lead orientation", "foundations_twelve_lead_navigation", "discriminate", "faded", { focus: "normal_ecg", receiptConcept: "normal_ecg", subskill: "discriminate", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "What can this representation show about shape, and what can it not show about timing?", hints: ["Read printed lead labels.", "A median composite is not a continuous rhythm strip."],
    }),
    buildScene({
      id: "S9", partId: "Chapter 3 · Twelve views and direction", minutes: 10, title: "Axis is the coarse QRS direction", objective: "Derive the frontal QRS quadrant from full-QRS polarity in I and aVF, then use lead II for leftward refinement.", setup: ["Axis is a directional summary of the mean frontal QRS. Use the full QRS area—not the T wave or tallest spike."], mechanism: ["Toward a lead’s positive pole projects positive; away projects negative.", "I and aVF establish the coarse quadrant.", "When I is positive and aVF negative, lead II refines the boundary near −30°."], clinicalHeading: "Direction before cause", clinicalBody: "Foundations reports the coarse direction. Fascicular, chamber, and conduction explanations belong to later modules.", transition: "Predict the geometry, reconstruct the quadrant table, then apply the lead-II boundary.", completionBody: "You can state a coarse frontal QRS direction without reversing the vector or overcalling the leftward boundary.", requirements: ["SPEC-11.6"], interactions: s9, caseContract: twelveLeadContrast("axis", "axis_normal", ["I", "II", "aVF"], "foundations:S9:component"),
      connections: { recallFrom: "S8 directed views and S6 full-QRS boundaries", changesNow: "Limb-lead polarity becomes a coarse direction", reuseNext: "M2 hexaxial refinement and M7/M5 mechanisms", clinicalUse: "Prevents aVF-negative from automatically becoming left-axis deviation" },
      handoffs: [handoff("train", "Focused · Coarse axis", "foundations_axis", "discriminate", "guided", { focus: "axis_normal", subskill: "discriminate" }), handoff("rapid", "Rapid · Axis quadrants", "foundations_axis", "recognize", "faded", { focus: "axis_normal", receiptConcept: "axis_normal", subskill: "recognize", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "What does the full QRS do in I, aVF, and—only when needed—lead II?", hints: ["Use the full QRS, not the T wave.", "I+/aVF− requires lead II refinement."],
    }),
    buildScene({
      id: "S10", partId: "Chapter 4 · Build the complete read", minutes: 12, title: "Put the full read together", objective: "Make a prediction at every step, preserve not-assessable findings, and rebuild the complete seven-step sequence.", setup: ["You learn more by committing to an answer before seeing an example interpretation."], mechanism: ["Each step builds on observations from earlier steps.", "After each answer, compare your reasoning with a concise example.", "The goal here is to build a reliable order you can use on a new ECG."], clinicalHeading: "A consistent sequence prevents omissions", clinicalBody: "The seven steps organize your read, but the patient’s clinical story still matters.", transition: "Make seven predictions, rebuild the sequence, then separate supported conclusions from overreach.", completionBody: "You have worked through the complete sequence. Next, you’ll repeat it with less guidance.", requirements: ["SPEC-11.16", "SPEC-12.1"], interactions: s10, caseContract: integratedContrast("foundations:S10:modeled"), minimumScore: 0.8, independent: false,
      connections: { recallFrom: "All S0–S9 component skills", changesNow: "Components become an ordered complete read", reuseNext: "S11 faded sweep and S12 integration", clinicalUse: "Reduces skipped domains and premature closure" },
      handoffs: [handoff("train", "Focused · Rehearse the seven-step sweep", "foundations_systematic_sweep", "synthesize", "guided", { focus: "integrated_interpretation", subskill: "synthesize" })], tutorPrompt: "Which earlier observation is the current conclusion relying on?", hints: ["Predict before reveal.", "Use not assessable when the representation lacks the required evidence."],
    }),
    buildScene({
      id: "S11", partId: "Chapter 4 · Build the complete read", minutes: 16, title: "Complete a read with less guidance", objective: "Work through all seven steps, connect each conclusion to the tracing, and write a concise summary.", setup: ["Prompts gradually disappear. Keep what is correct and revise only the first conclusion that the ECG does not support."], mechanism: ["Answer every step or explain why it is not assessable.", "Connect rate, source, axis, intervals, and recovery to the relevant ECG finding.", "Write the summary only after those links make sense."], clinicalHeading: "Show what supports each conclusion", clinicalBody: "Even a correct phrase needs the right lead, waveform, or measurement behind it.", transition: "Complete the seven steps, match conclusions to findings, then write your summary.", completionBody: "You completed the full read with less guidance. One final lesson will ask you to apply it twice.", requirements: ["SPEC-11.16", "SPEC-12.1"], interactions: s11, caseContract: integratedContrast("foundations:S11:guided"), minimumScore: 0.8, independent: false,
      connections: { recallFrom: "S10 active modeled sweep", changesNow: "Prompts fade and evidence links become explicit", reuseNext: "S12 immediate integration and mixed practice", clinicalUse: "Produces a reviewable, uncertainty-aware ECG description" },
      handoffs: [handoff("train", "Focused · Complete ECG sweep", "foundations_systematic_sweep", "synthesize", "faded", { focus: "integrated_interpretation", subskill: "synthesize" }), handoff("rapid", "Rapid · Whole-ECG structure", "foundations_systematic_sweep", "synthesize", "faded", { focus: "integrated_interpretation", receiptConcept: "integrated_interpretation", subskill: "synthesize", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "Which clause lacks a direct lead, mark, measurement, or unavailable reason?", hints: ["Keep every valid clause.", "Change only the first unsupported domain, then continue."],
    }),
    buildScene({
      id: "S12", partId: "Chapter 4 · Build the complete read", minutes: 18, title: "Two complete ECG reads", objective: "Apply all seven steps to two ECGs, connect each conclusion to a finding, and state uncertainty clearly.", setup: ["This final lesson brings every Foundations skill together. Work through each ECG without skipping an unclear step."], mechanism: ["ECG 1 uses the blank seven-step sequence.", "ECG 2 asks you to match conclusions to findings before writing the final summary.", "After Foundations, practise the same process on new ECGs so it becomes fluent."], clinicalHeading: "A complete read is the start of clinical reasoning", clinicalBody: "A systematic ECG description supports the next clinical decision; it does not replace the patient’s history, examination, or supervised judgment.", transition: "Complete both reads, preserve not-assessable findings, and be confident only where the tracing supports you.", completionBody: "You completed Foundations. Continue to Leads & Vectors, or practise any lesson you marked for review.", requirements: ["SPEC-11.16", "SPEC-12.1", "SPEC-7.normal_ecg"], interactions: s12, caseContract: integratedContrast("foundations:S12:integration"), minimumScore: 0.8, independent: false,
      connections: { recallFrom: "S11 faded evidence notebook", changesNow: "Two complete reads are integrated with confidence calibration", reuseNext: "M2 Leads & Vectors, Focused Practice, Rapid Practice, and later retention", clinicalUse: "Creates a defensible descriptive baseline for later diagnostic reasoning" },
      handoffs: [handoff("train", "Focused · Review a Foundations skill", "foundations_systematic_sweep", "synthesize", "faded", { focus: "integrated_interpretation", subskill: "synthesize" }), handoff("rapid", "Rapid · Mixed Foundations practice", "foundations_systematic_sweep", "synthesize", "faded", { focus: "integrated_interpretation", receiptConcept: "integrated_interpretation", subskill: "synthesize", pace: "untimed", suggestedLength: 5 })], tutorPrompt: "Which conclusion in your final line has the weakest support from the ECG?", hints: ["Open the tutor only after committing your own read.", "A supported not-assessable statement receives full credit for that unavailable part."],
    }),
  ],
};
