import type { LearningInteraction, ProductionModule } from "@/lib/learning/interactionTypes";
import {
  accessibility,
  buildScene,
  caseSpec,
  compactInteraction,
  feedback,
  handoff,
  responsiveLayout,
  sceneCopy,
  sources,
  tutorContract,
} from "@/lib/learning/modules/m07M10ModuleHelpers";

const access = (instructions: string, summary: string, reducedMotion?: string) =>
  accessibility({
    instructions,
    keyboard:
      "Tab reaches controls in visual order. Arrow keys move the selected handle by one small box; Shift+Arrow moves five. Enter anchors a mark. Every drag also has select, step, and confirm controls.",
    summary,
    reducedMotion,
  });

const s0Feedback = feedback({
  correct:
    "Exactly. Mass, vector alignment, distance, and lead position can all alter voltage. The tracing supplies electrical evidence; anatomy still needs corroboration.",
  partial:
    "You isolated [credited variable], but [uncontrolled variable] also moved. Reset and test one cause at a time.",
  incorrect:
    "The vector now points [toward/away from] [lead]. Predict the projection before using amplitude as a size claim.",
  unsafe:
    "That conclusion outruns the model. No simulated voltage alone proves hypertrophy or dictates treatment. Return to the cause→signal relationship.",
  notAssessable:
    "Not assessable is correct for wall thickness. The model exposes voltage and each causal control, so the signal change is assessable.",
  evidenceCue: "Hold three controls fixed and inspect the named lead projection.",
});

const s0Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s0-causal-model",
    kind: "model_explore",
    prompt: "Change one cause at a time and inspect the recorded lead.",
    instructions:
      "Visit all four frames. Before each reveal, predict whether the selected lead becomes larger, smaller, or changes direction.",
    subskills: ["explain_mechanism", "measure"],
    feedback: s0Feedback,
    accessibility: access(
      "Use named Mass, Direction, Distance, and Lead position frames; motion is optional.",
      "A four-frame vector-projection model compares muscle contribution, vector direction, electrode distance, and lead position while other variables remain fixed.",
      "Show four numbered before/after frames with exact amplitude values and no moving vector.",
    ),
    model: "vector_projection",
    frames: [
      { id: "mass", label: "Muscle contributing to the vector", narration: "Increase contributing muscle while direction, distance, and lead position stay fixed.", vectorAngleDeg: 20, waveformLabel: "Recorded amplitude" },
      { id: "direction", label: "Vector direction", narration: "Rotate the net vector while mass, distance, and lead position stay fixed.", vectorAngleDeg: 120, waveformLabel: "Projection may shrink or reverse" },
      { id: "distance", label: "Electrode distance", narration: "Increase distance while mass, direction, and lead position stay fixed.", vectorAngleDeg: 20, waveformLabel: "Recorded amplitude decreases" },
      { id: "placement", label: "Lead position", narration: "Move the observing lead while cardiac mass, vector, and distance are held by the model.", vectorAngleDeg: 20, waveformLabel: "Lead-specific projection changes" },
    ],
    requiredFrameIds: ["mass", "direction", "distance", "placement"],
  }),
  compactInteraction({
    id: "m07-s0-amplitude",
    kind: "numeric_entry",
    prompt: "Measure the resulting amplitude in the requested lead.",
    instructions: "Place an amplitude caliper from baseline to peak, then enter millivolts.",
    subskills: ["measure", "explain_mechanism"],
    feedback: s0Feedback,
    accessibility: access(
      "Select the lead, set baseline and peak with steppers, and enter the measured amplitude.",
      "The selected lead, fixed variables, and resulting amplitude are announced after each confirmed model state.",
    ),
    label: "Recorded amplitude",
    unit: "mV",
    target: { source: "authored_simulation", measurementKey: "recorded_amplitude_mv", tolerance: 0.05 },
    minimum: 0,
    maximum: 5,
  }),
  compactInteraction({
    id: "m07-s0-vector-prediction",
    kind: "vector_lab",
    prompt: "Rotate the net vector away from lead I while mass and distance remain fixed.",
    instructions: "Set the target direction, then predict polarity in lead I and aVF before revealing the projections.",
    subskills: ["explain_mechanism", "localize"],
    feedback: s0Feedback,
    accessibility: access(
      "Rotate with Left/Right 15-degree buttons or enter the target angle; choose polarity for each lead from text controls.",
      "The initial and target angles, lead-I projection, and aVF projection are announced.",
      "Show initial and target vectors as two static labeled arrows with a polarity table.",
    ),
    initialAngleDeg: 20,
    targetAngleDeg: 120,
    toleranceDeg: 15,
    targetLabel: "Vector turned away from lead I",
    predictions: [
      { lead: "I", expected: "negative" },
      { lead: "aVF", expected: "positive" },
    ],
  }),
];

const s1Feedback = feedback({
  correct:
    "Supported. In [case], [lead-II evidence] and [V1 evidence] together support [normalized atrial-pattern description] at [confidence]. You used morphology across leads rather than a nickname.",
  partial:
    "Your lead-II boundary is supported. The atrial-pattern claim remains locked until you mark the initial and terminal components in V1.",
  incorrect:
    "You marked the QRS onset as the end of P. Return to the P wave’s final baseline crossing, then re-evaluate its duration and contour.",
  unsafe:
    "A P-wave clue does not prove a cause, chamber pressure, or treatment need. State the supported atrial pattern and its limitation.",
  notAssessable:
    "Good restraint when noise obscures a component. Lead [lead] contains a validated readable P-wave component in the core case, so mark it before choosing not assessable there.",
  evidenceCue: "Use lead II for the whole P wave and V1 for initial versus terminal components.",
});

const s1Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s1-p-duration",
    kind: "caliper",
    prompt: "Mark P onset and P end in lead II.",
    instructions: "Measure the whole P wave from onset to its final return to baseline.",
    subskills: ["measure", "recognize"],
    feedback: s1Feedback,
    accessibility: access(
      "Use Start P and End P buttons or millisecond steppers in lead II.",
      "The structured P-wave row announces onset, end, duration, and signal-quality status.",
    ),
    measurement: "custom",
    target: { source: "packet_measurement", measurementKey: "p_duration_ms", toleranceMs: 20, lead: "II" },
    requireBoundaryLabels: true,
  }),
  compactInteraction({
    id: "m07-s1-v1-components",
    kind: "region",
    prompt: "Separate the initial and terminal portions of the V1 P wave.",
    instructions: "Draw regions over the initial positive and terminal negative components; confirm each region.",
    subskills: ["localize", "discriminate"],
    feedback: s1Feedback,
    accessibility: access(
      "Choose Initial positive component and Terminal negative component from the V1 landmark list, then confirm their time ranges.",
      "Lead V1 is represented as ordered initial and terminal P-wave components with polarity and duration.",
    ),
    concept: "atrial_p_components_v1",
    allowedLeads: ["V1"],
    minimumDurationMs: 20,
  }),
  compactInteraction({
    id: "m07-s1-atrial-evidence",
    kind: "categorize",
    prompt: "Assign each marked feature to the evidence it supports.",
    instructions: "Use the paired lead evidence; do not infer etiology.",
    subskills: ["discriminate", "calibrate_confidence"],
    feedback: s1Feedback,
    accessibility: access(
      "For each feature, choose right-atrial clue, left-atrial clue, normal/reference, or not reliably measurable.",
      "A table lists every lead-specific feature and its selected evidence category.",
    ),
    items: [
      { id: "ii-duration", label: "Lead-II duration and contour" },
      { id: "v1-initial", label: "V1 initial component" },
      { id: "v1-terminal", label: "V1 terminal component" },
    ],
    categories: [
      { id: "right-clue", label: "Right-atrial clue" },
      { id: "left-clue", label: "Left-atrial clue" },
      { id: "reference", label: "Normal / within reference" },
      { id: "limited", label: "Not reliably measurable" },
    ],
    correctCategoryByItem: { "ii-duration": "left-clue", "v1-initial": "right-clue", "v1-terminal": "left-clue" },
  }),
];

const s2Feedback = feedback({
  correct:
    "Supported. You measured [components], calculated [sum], and interpreted it with [corroboration] plus [limitation]. The strongest defensible wording is: ‘[normalized claim].’",
  partial:
    "The voltage sum is correct. Add one corroborating feature and one reason voltage may mislead before the claim can complete.",
  incorrect:
    "The S wave was measured peak-to-trough. Return to the baseline, measure its depth, and recalculate.",
  unsafe:
    "Voltage alone does not prove anatomical LVH, hypertension, or a treatment decision. Replace certainty with the supported ECG-pattern wording.",
  notAssessable:
    "Correct when gain or lead limitations invalidate the criterion. With standard gain and all criterion leads present, the voltage calculation is assessable; anatomical wall thickness is not.",
  evidenceCue: "Verify calibration, measure from baseline, then add corroboration and a limitation.",
});

const s2Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s2-calibration",
    kind: "point",
    prompt: "Verify the calibration pulse before measuring voltage.",
    instructions: "Select the calibration pulse and confirm the displayed gain.",
    subskills: ["localize", "measure"],
    feedback: s2Feedback,
    accessibility: access(
      "Choose Calibration pulse from the structured recording landmarks and confirm gain.",
      "The calibration pulse, paper gain, and validity for amplitude measurement are announced.",
    ),
    concept: "calibration_pulse",
    gradePrompt: "Select the calibration pulse that validates amplitude measurement.",
  }),
  compactInteraction({
    id: "m07-s2-voltage-sum",
    kind: "numeric_entry",
    prompt: "Populate the reviewed LVH voltage equation.",
    instructions: "Measure each R or S from the local baseline and enter the criterion sum in millivolts.",
    subskills: ["measure", "synthesize"],
    feedback: s2Feedback,
    accessibility: access(
      "Use the required-lead table, baseline-to-peak steppers, and automatic arithmetic.",
      "The accessible equation names each lead component, value, sum, policy version, and validity status.",
    ),
    label: "Reviewed LVH criterion sum",
    unit: "mV",
    target: { source: "packet_measurement", measurementKey: "lvh_voltage_sum_mv", tolerance: 0.1 },
    minimum: 0,
    maximum: 10,
  }),
  compactInteraction({
    id: "m07-s2-evidence-bundle",
    kind: "categorize",
    prompt: "Build the LVH evidence bundle and its limits.",
    instructions: "Classify visible factors as corroborating evidence or limitations; both are required.",
    subskills: ["discriminate", "calibrate_confidence"],
    feedback: s2Feedback,
    accessibility: access(
      "Assign each case factor using a dropdown; at least one corroboration and one limitation must be represented.",
      "A two-column evidence table separates corroboration from factors that reduce voltage specificity.",
    ),
    items: [
      { id: "axis", label: "Axis / force pattern" },
      { id: "repolarization", label: "Lateral repolarization pattern" },
      { id: "context", label: "Age, body habitus, or athletic context" },
      { id: "placement", label: "Lead placement and gain" },
    ],
    categories: [
      { id: "corroborates", label: "Corroborates the pattern" },
      { id: "limits", label: "Limits specificity or validity" },
    ],
    correctCategoryByItem: { axis: "corroborates", repolarization: "corroborates", context: "limits", placement: "limits" },
  }),
];

const s3Feedback = feedback({
  correct:
    "Supported. [Axis evidence], [V1/precordial evidence], and [corroboration] form an RVH-compatible pattern. You also excluded [mimic] from its decisive feature.",
  partial:
    "You found the dominant R in V1. Now determine whether it is the main force or a late conduction force by checking QRS width and lateral terminal morphology.",
  incorrect:
    "The boxed deflection is terminal and paired with [lateral feature], which favors a conduction pattern over an RVH claim.",
  unsafe:
    "A tall R in V1 cannot by itself prove RVH, pulmonary disease, or posterior infarction. State the supported pattern and unresolved alternative.",
  notAssessable:
    "Correctly limited when required evidence is missing. Axis, QRS duration, and paired precordial/lateral morphology are available in the core case and must be completed.",
  evidenceCue: "Combine axis, V1 R/S balance, progression, and terminal QRS morphology.",
});

const s3Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s3-axis-leads",
    kind: "lead_select",
    prompt: "Select the leads required to establish frontal direction and the V1/lateral contrast.",
    instructions: "Select I, aVF, V1, and V6 before measuring the pattern.",
    subskills: ["localize", "discriminate"],
    feedback: s3Feedback,
    accessibility: access(
      "Choose leads from an anatomical checklist in frontal-then-precordial order.",
      "Selected frontal and precordial lead evidence is announced by lead name and role.",
    ),
    selectionMode: "multiple",
    correctLeads: ["I", "aVF", "V1", "V6"],
    allowedLeads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V5", "V6"],
    rejectExtraSelections: true,
  }),
  compactInteraction({
    id: "m07-s3-v1-rs",
    kind: "numeric_entry",
    prompt: "Measure the V1 R/S ratio from the local baseline.",
    instructions: "Enter R amplitude divided by S amplitude; then inspect whether the force persists across V1–V6.",
    subskills: ["measure", "discriminate"],
    feedback: s3Feedback,
    accessibility: access(
      "Enter R and S amplitudes using steppers; the form calculates the ratio.",
      "Lead V1 R amplitude, S amplitude, ratio, and QRS-width context are announced.",
    ),
    label: "V1 R/S ratio",
    unit: "ratio",
    target: { source: "packet_measurement", measurementKey: "v1_rs_ratio", tolerance: 0.15 },
    minimum: 0,
    maximum: 10,
  }),
  compactInteraction({
    id: "m07-s3-terminal-mimic",
    kind: "region",
    prompt: "Box any terminal bundle-delay morphology that changes the RVH interpretation.",
    instructions: "Inspect V1 and a lateral lead; mark the late terminal force rather than the tallest deflection.",
    subskills: ["localize", "discriminate"],
    feedback: s3Feedback,
    accessibility: access(
      "Choose the named terminal-QRS segment in V1 or V6 from the lead-region list.",
      "The structured view distinguishes the dominant initial/main force from a late terminal force.",
    ),
    concept: "rbbb_terminal_force_mimic",
    allowedLeads: ["V1", "V2", "I", "V6"],
    minimumDurationMs: 20,
  }),
];

const s4Feedback = feedback({
  correct:
    "Correct. Transition occurs at [lead], with [smooth/early/late/nonmonotonic] progression across V1–V6. That is the supported descriptive claim.",
  partial:
    "You identified [lead] as transition, but [missing lead] has no R/S measurement. Complete the sequence so the pattern is reproducible.",
  incorrect:
    "R becomes larger than S first in [lead], not the lead with the tallest absolute R. Recheck the ratios.",
  unsafe:
    "Poor progression is a description, not an infarction diagnosis. Save etiology for the differential and lead-evidence checks.",
  notAssessable:
    "Correct when a lead is unreadable or misidentified. With all six calibrated and readable leads, measure the R/S sequence before using not assessable.",
  evidenceCue: "Measure every precordial lead and identify the first R/S ratio above one.",
});

const s4Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s4-lead-order",
    kind: "sequence",
    prompt: "Build the precordial sweep in anatomical order.",
    instructions: "Order V1 through V6 before tracing the R/S balance.",
    subskills: ["localize", "recognize"],
    feedback: s4Feedback,
    accessibility: access(
      "Use Move earlier and Move later controls to order the six lead cards.",
      "The ordered list announces V1 through V6 and flags any lead-identity mismatch.",
    ),
    cards: ["V1", "V2", "V3", "V4", "V5", "V6"].map((lead) => ({ id: lead.toLowerCase(), label: lead })),
    correctOrder: ["v1", "v2", "v3", "v4", "v5", "v6"],
  }),
  compactInteraction({
    id: "m07-s4-progression-compare",
    kind: "compare",
    prompt: "Compare a common transition with a late/poor-progression sequence.",
    instructions: "Complete the R/S description for all six leads, then name transition and sequence quality.",
    subskills: ["measure", "discriminate"],
    feedback: s4Feedback,
    accessibility: access(
      "Use a six-row R/S table for each case; no visual scrub is required.",
      "Each case is summarized by lead-level R dominance, S dominance, balance, and first R greater than S.",
    ),
    leftCaseConcept: "normal_r_wave_progression",
    rightCaseConcept: "poor_r_wave_progression",
    dimensions: [
      { id: "v1-v2", label: "V1–V2 balance", leftAnswer: "S-dominant", rightAnswer: "S-dominant" },
      { id: "transition", label: "First R > S", leftAnswer: "V3–V4", rightAnswer: "Late or absent" },
      { id: "sequence", label: "Sequence", leftAnswer: "Smooth growth", rightAnswer: "Delayed or nonmonotonic" },
    ],
  }),
];

const s5Feedback = feedback({
  correct:
    "Well calibrated. This ECG shows [progression description]. [Decisive evidence] makes [best explanation] the strongest supported category, while [alternative] remains [plausible/unsupported].",
  partial:
    "The progression description is correct. The cause remains unlocked because [placement/prior/conduction] has not been checked.",
  incorrect:
    "Poor R-wave progression alone does not establish prior anterior infarction. Mark territorial Q-wave/statement evidence or keep the conclusion descriptive.",
  unsafe:
    "Do not create an acute or causal claim from this resting pattern. The supported output is a descriptive finding plus the next verification step.",
  notAssessable:
    "Correctly limited when comparison is invalid. Current progression is still describable even when old-versus-new is not.",
  evidenceCue: "Audit acquisition, conduction, chamber context, and comparison validity before cause.",
});

const s5Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s5-current-prior",
    kind: "compare",
    prompt: "Compare current progression with a prior or corrected reacquisition.",
    instructions: "Verify identical gain, lead order, and placement before identifying change.",
    subskills: ["discriminate", "calibrate_confidence"],
    feedback: s5Feedback,
    accessibility: access(
      "Use the matched-lead table and comparison-validity fields instead of the ghost overlay.",
      "Current and prior V1–V6 progression, gain, lead order, placement, and validity are summarized row by row.",
    ),
    leftCaseConcept: "poor_r_wave_progression_current",
    rightCaseConcept: "prior_or_reacquired_progression",
    dimensions: [
      { id: "gain", label: "Gain", leftAnswer: "Current gain", rightAnswer: "Must match" },
      { id: "placement", label: "Chest-lead placement", leftAnswer: "Verify", rightAnswer: "Corrected or comparable" },
      { id: "qrs", label: "Whole-QRS morphology", leftAnswer: "Describe", rightAnswer: "Compare matched leads" },
      { id: "change", label: "Temporal claim", leftAnswer: "Current finding", rightAnswer: "Only if comparison valid" },
    ],
  }),
  compactInteraction({
    id: "m07-s5-differential",
    kind: "categorize",
    prompt: "Place each case in the strongest supported differential category.",
    instructions: "Use acquisition, QRS morphology, chamber evidence, and territorial evidence—not progression alone.",
    subskills: ["discriminate", "synthesize"],
    feedback: s5Feedback,
    accessibility: access(
      "Choose one category and one next check for each case from labeled lists.",
      "Every case row contains progression description, decisive evidence, selected differential, and next check.",
    ),
    items: [
      { id: "placement-case", label: "Progression normalizes after corrected placement" },
      { id: "rotation-case", label: "Stable late transition with valid prior" },
      { id: "conduction-case", label: "Poor progression with wide-QRS conduction pattern" },
      { id: "territory-case", label: "Progression plus eligible territorial Q-wave evidence" },
    ],
    categories: [
      { id: "acquisition", label: "Acquisition / placement" },
      { id: "variation", label: "Normal variation / rotation" },
      { id: "conduction", label: "Conduction" },
      { id: "prior-possible", label: "Prior infarction possible" },
    ],
    correctCategoryByItem: { "placement-case": "acquisition", "rotation-case": "variation", "conduction-case": "conduction", "territory-case": "prior-possible" },
  }),
];

const s6Feedback = feedback({
  correct:
    "Correct. [Leads] show recovery discordant to their dominant QRS and compatible with a secondary pattern. [Outlier] is not safely dismissed and needs separate assessment.",
  partial:
    "Your T direction is correct, but the dominant QRS direction is missing. Establish activation before classifying recovery.",
  incorrect:
    "In [lead], QRS points [direction] while ST/T points [opposite]. That relationship is discordant, not concordant.",
  unsafe:
    "Neither ‘all expected’ nor an acute diagnosis is supported here. Mark what the activation pattern explains and what still needs separate assessment.",
  notAssessable:
    "Correctly limited when a baseline is unstable. QRS and T polarity are readable in the core leads even though etiology beyond secondary change is not.",
  evidenceCue: "Read QRS direction first, then ST/T direction, then compare.",
});

const s6Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s6-direction-pairs",
    kind: "pairing",
    prompt: "Pair each dominant QRS direction with the observed recovery direction.",
    instructions: "Use at least three leads; classify the relation only after both directions are marked.",
    subskills: ["discriminate", "explain_mechanism"],
    feedback: s6Feedback,
    accessibility: access(
      "Choose QRS and ST/T direction text values for each named lead.",
      "Each lead is announced as QRS positive/negative, ST/T positive/negative, and concordant/discordant.",
    ),
    left: [
      { id: "v5-qrs", label: "V5 dominant positive QRS" },
      { id: "v6-qrs", label: "V6 dominant positive QRS" },
      { id: "avl-qrs", label: "aVL dominant positive QRS" },
    ],
    right: [
      { id: "v5-recovery", label: "V5 depressed ST / negative T" },
      { id: "v6-recovery", label: "V6 depressed ST / negative T" },
      { id: "avl-recovery", label: "aVL depressed ST / negative T" },
    ],
    correctPairs: { "v5-qrs": "v5-recovery", "v6-qrs": "v6-recovery", "avl-qrs": "avl-recovery" },
  }),
  compactInteraction({
    id: "m07-s6-outlier",
    kind: "region",
    prompt: "Box the recovery change that is not explained by the activation pattern.",
    instructions: "Mark the superimposed outlier and label it needs separate assessment.",
    subskills: ["localize", "calibrate_confidence"],
    feedback: s6Feedback,
    accessibility: access(
      "Select the named lead and beat segment from the outlier-region list, then confirm.",
      "The outlier lead, time interval, activation context, and need for separate assessment are announced.",
    ),
    concept: "superimposed_primary_repolarization_change",
    allowedLeads: ["I", "aVL", "V5", "V6", "V1"],
    minimumDurationMs: 40,
  }),
];

const s7Feedback = feedback({
  correct:
    "Supported. Your marks demonstrate [evidence sentence]. ‘[normalized synthesis]’ is the strongest claim this packet allows.",
  partial:
    "You have [credited evidence]. The synthesis remains locked until [missing independent domain] is demonstrated.",
  incorrect:
    "Your conclusion depends on [weak feature], while [decisive mimic/limitation] argues against that specificity. Rebuild the bundle.",
  unsafe:
    "This resting ECG does not support an acute diagnosis, causal disease statement, or treatment order. Return to the chamber/progression evidence.",
  notAssessable:
    "Correctly limited when the packet withholds a required domain. Readable required leads must be completed before limiting the conclusion.",
  evidenceCue: "Use calibration, two diagnostic regions, one measurement, corroboration, limitation, and confidence.",
});

const s7Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m07-s7-evidence-leads",
    kind: "lead_select",
    prompt: "Select the two most diagnostic lead regions for this unannounced case.",
    instructions: "Choose evidence from independent domains rather than two copies of the same voltage clue.",
    subskills: ["localize", "discriminate"],
    feedback: s7Feedback,
    accessibility: access(
      "Use the full lead checklist and describe the selected feature in each lead.",
      "Selected leads and their independent evidence domains are announced before synthesis.",
    ),
    selectionMode: "multiple",
    correctLeads: ["V1", "V6"],
    allowedLeads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"],
    rejectExtraSelections: false,
  }),
  compactInteraction({
    id: "m07-s7-synthesis",
    kind: "free_response",
    prompt: "Submit one evidence-limited chamber/progression interpretation.",
    instructions: "Name the measured criterion or morphology, corroboration, mimic/limit, and confidence.",
    subskills: ["synthesize", "calibrate_confidence"],
    feedback: s7Feedback,
    accessibility: access(
      "Type or dictate using the evidence sentence frame; speech is graded on claims, not accent or style.",
      "The response is checked for supported evidence, corroboration, limitation, and calibrated conclusion.",
    ),
    responseLabel: "Evidence-limited synthesis",
    placeholder: "This ECG shows … in …, supported by …; however …, so confidence is …",
    minimumCharacters: 45,
    sentenceFrame: "This ECG shows [pattern] from [lead evidence], supported by [corroboration]; [limit], so confidence is [level].",
    rubric: [
      { id: "direct-evidence", label: "Names direct waveform evidence and leads", acceptedConcepts: ["atrial_enlargement", "left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "r_wave_progression"], required: true, misconceptionIfMissing: "label_without_evidence" },
      { id: "corroboration", label: "Adds an independent corroborating domain", acceptedConcepts: ["axis", "qrs_context", "repolarization_context", "valid_prior"], required: true },
      { id: "limit", label: "States a mimic or evidence ceiling", acceptedConcepts: ["lead_placement", "normal_variation", "conduction_mimic", "not_assessable"], required: true, misconceptionIfMissing: "single_criterion_overcall" },
      { id: "confidence", label: "States calibrated confidence", acceptedConcepts: ["low_confidence", "moderate_confidence", "high_confidence"], required: true },
    ],
  }),
];

export const M07_CHAMBERS_VOLTAGE_MODULE: ProductionModule = {
  id: "chambers-voltage",
  order: 7,
  title: "Chambers, Voltage, and R-Wave Progression",
  shortTitle: "Chambers & voltage",
  duration: "50–65 min",
  outcome:
    "Describe atrial and ventricular chamber evidence, assess R-wave progression, distinguish secondary recovery, and avoid diagnosis from one weak criterion.",
  prerequisiteIds: ["leads-vectors", "ventricular-conduction"],
  accent: "#B96B3C",
  sourceRequirementIds: [
    "SPEC-CHAMBER-ELIGIBILITY",
    "ARCH-M7",
    "INV-R-CHAMBER",
    "SPEC-11.9",
    "SPEC-11.10",
  ],
  scenes: [
    buildScene({
      id: "m07-s0",
      partId: "m07-part-1",
      minutes: 6,
      source: sources("M7-S0", ["SPEC-CHAMBER-ELIGIBILITY", "SPEC-VIEWER", "ARCH-M7", "V2-CHAMBERS", "INV-R-SYNTH"]),
      copy: sceneCopy({
        eyebrow: "M7 · 1 of 8",
        title: "Voltage is a projection",
        objective: "Predict how mass, direction, distance, and lead position alter the recorded signal.",
        openingTutorMessage: "Change one cause at a time. Predict the lead’s response before moving the control.",
        setup: ["A lead records the projection of electrical activity toward or away from it. More activated muscle can increase voltage, but so can a better-aligned vector or a closer electrode."],
        mechanismNarration: ["Distance, tissue, lead position, activation sequence, and cancellation can reduce it. Voltage is evidence about electrical forces—not a direct measurement of wall thickness.", "Muscle contributing to the vector · Vector direction · Electrode distance · Lead position · Recorded amplitude · Hold other variables constant."],
        clinicalConnectionHeading: "Electrical evidence, not an echocardiogram",
        clinicalConnectionBody: "Anatomical wall thickness still needs corroboration.",
        transitionIntoTask: "Make a prediction before you reveal the mechanism.",
        completionBody: "Mass, vector alignment, distance, and lead position are now separated as causes of recorded voltage.",
      }),
      layout: responsiveLayout("The torso model sits left and synchronized lead panels right; a one-variable tray is below. Mobile presents Change mass, Change direction, and Change distance as numbered cards."),
      tutor: tutorContract({ socratic: "If wall mass stays constant but the vector turns away from a lead, what should that lead record?", hints: ["A lead sees only the component of the vector aligned with that lead.", "Distance and intervening tissue alter recorded amplitude without changing myocardium."], returnPrompt: "Back to [variable]: keep the other three controls fixed, then measure [lead]." }),
      caseContract: caseSpec({ selectorLessonId: "hypertrophy", requestedConcept: "chamber_voltage_projection", minimumTier: "A", requiredEvidence: ["Authored wall-mass parameter", "Net vector", "Lead coordinates", "Distance/attenuation", "Expected amplitude"], requiredLeads: ["I", "aVL", "V1", "V3", "V5", "V6"], allowedUses: ["mechanism", "measurement"], fallback: "authored_simulation", forbiddenClaims: ["Hypertrophy diagnosis from model voltage", "Treatment"] }),
      interactions: s0Interactions,
      minimumScore: 0.9,
      connections: { recallFrom: "M2 vector projection", changesNow: "Mass, direction, distance, and placement become independently manipulable voltage causes", reuseNext: "M7 atrial/LVH/RVH criteria", clinicalUse: "Prevents voltage-equals-anatomy reasoning" },
      handoffs: [handoff("train", "Train · Voltage causes", "chamber_voltage_projection", "explain_mechanism", "guided")],
    }),
    buildScene({
      id: "m07-s1", partId: "m07-part-1", minutes: 7,
      source: sources("M7-S1", ["SPEC-ONTOLOGY", "SPEC-CHAMBER-ELIGIBILITY", "ARCH-M7", "INV-R-CHAMBER"]),
      copy: sceneCopy({ eyebrow: "M7 · 2 of 8", title: "Atrial evidence lives in P-wave shape", objective: "Use lead II and V1 morphology without turning one P-wave feature into an anatomical certainty.", openingTutorMessage: "Start with the whole P wave in II, then inspect the terminal component in V1.", setup: ["The P wave combines right- and left-atrial activation. Lead II helps show its overall duration and contour; V1 often separates an initial anterior/rightward component from a terminal posterior/leftward component."], mechanismNarration: ["Broad, notched, tall, or prominent terminal components are clues. They support an atrial-abnormality pattern only when signal, calibration, lead identity, and corroborating evidence are trustworthy."], clinicalConnectionHeading: "A clue, not a cause", clinicalConnectionBody: "Atrial-pattern evidence can fit chronic pressure or volume loading, but the ECG does not establish the cause. Echo, history, rhythm, and prior ECGs can change the interpretation.", transitionIntoTask: "Mark lead II first, then divide the V1 components.", completionBody: "Lead-II duration/contour and V1 component evidence now support an evidence-limited atrial-pattern description." }),
      layout: responsiveLayout("Linked lead-II and V1 magnifiers sit above a two-row atrial timeline. Mobile uses a synchronized II/V1 toggle and persistent evidence tray."),
      tutor: tutorContract({ socratic: "Which part of the V1 P wave points posteriorly and therefore can carry left-atrial evidence?", hints: ["Use onset and final return to baseline—not the peak—to measure duration.", "In V1, separate the initial positive portion from the terminal negative portion before naming a clue."], returnPrompt: "Back to [case], [lead]: finish the P-wave boundary before assigning the chamber clue." }),
      caseContract: caseSpec({ selectorLessonId: "hypertrophy", requestedConcept: "atrial_enlargement", minimumTier: "A", requiredEvidence: ["Compatible atrial statement", "Readable P morphology or validated fiducials", "Lead-II P duration/contour", "V1 initial and terminal components", "Signal quality"], requiredLeads: ["II", "V1"], allowedUses: ["measurement", "scored_recognition"], fallback: "authored_simulation", forbiddenClaims: ["Atrial anatomy from one P feature", "Etiology or treatment"] }),
      interactions: s1Interactions, minimumScore: 0.85,
      connections: { recallFrom: "M1 P-wave boundaries and M3 atrial-event recognition", changesNow: "P morphology becomes distributed chamber evidence across II and V1", reuseNext: "M7 chamber transfer", clinicalUse: "Supports cautious correlation with echo, rhythm, and history" },
      handoffs: [handoff("train", "Train · P-wave chamber contrasts", "atrial_enlargement", "discriminate", "faded")],
    }),
    buildScene({
      id: "m07-s2", partId: "m07-part-2", minutes: 8,
      source: sources("M7-S2", ["SPEC-CHAMBER-ELIGIBILITY", "ARCH-M7", "INV-R-CHAMBER", "INV-R-CLINREV"]),
      copy: sceneCopy({ eyebrow: "M7 · 3 of 8", title: "LVH is an evidence bundle", objective: "Measure voltage correctly, apply a reviewed criterion, and seek corroboration.", openingTutorMessage: "Check the calibration pulse before adding any millivolts.", setup: ["LVH voltage criteria compress a three-dimensional signal into a screening rule. Sokolow–Lyon adds S in V1 to the larger R in V5 or V6. Cornell voltage combines R in aVL with S in V3 and interprets the sum using its reviewed context threshold."], mechanismNarration: ["A positive criterion raises support; it does not measure wall thickness or establish a cause.", "[criterion display name] · [formula] · Reviewed threshold: [threshold and population context] · Policy version [version] · reviewed [date] · Use only with standard gain and eligible leads."], clinicalConnectionHeading: "Criterion + corroboration + limitation", clinicalConnectionBody: "Voltage criterion · Axis/force pattern · Lateral repolarization pattern · Compatible statement/prior · Age/body habitus/athletic context · Lead placement and gain.", transitionIntoTask: "Verify gain, measure from baseline, calculate, then audit the evidence bundle.", completionBody: "A reviewed LVH criterion is interpreted with corroboration and an explicit limitation." }),
      layout: responsiveLayout("Full 12-lead remains visible with a pinned five-lead tray and live criterion equation. Mobile opens required leads at identical scale with a pinned running sum."),
      tutor: tutorContract({ socratic: "If the voltage sum crosses a threshold, what second piece of evidence would make the pattern more persuasive?", hints: ["Measure each deflection from the local baseline, not peak to trough.", "The formula tells you which leads to combine; the case contract tells you whether the criterion may be used."], returnPrompt: "Back to [criterion]: verify gain, then finish [lead] before interpreting the sum." }),
      caseContract: caseSpec({ selectorLessonId: "hypertrophy", requestedConcept: "left_ventricular_hypertrophy", minimumTier: "A", requiredEvidence: ["Calibrated voltage or raw amplitude", "Compatible LVH statement", "Approved criterion policy", "At least one corroborating field", "Variant or gain trap"], requiredLeads: ["V1", "V3", "V5", "V6", "aVL"], allowedUses: ["measurement", "scored_recognition", "transfer"], fallback: "lock_scene", forbiddenClaims: ["Anatomical LVH from voltage alone", "Unreviewed threshold", "Hypertension diagnosis or treatment"] }),
      interactions: s2Interactions, minimumScore: 0.88,
      connections: { recallFrom: "M7-S0 projection and M2 axis", changesNow: "A versioned voltage rule is embedded in an evidence bundle", reuseNext: "M7 strain and M9 LVH mimic", clinicalUse: "Distinguishes a screening pattern from anatomical certainty" },
      handoffs: [handoff("train", "Train · LVH voltage with mimics", "left_ventricular_hypertrophy", "discriminate", "faded"), handoff("clinical", "Clinical · Pre-op abnormal voltage", "lvh_chronic_context", "apply_in_context", "guided")],
    }),
    buildScene({
      id: "m07-s3", partId: "m07-part-2", minutes: 8,
      source: sources("M7-S3", ["SPEC-CHAMBER-ELIGIBILITY", "ARCH-M7", "INV-R-CHAMBER", "SPEC-MISCONCEPTIONS"]),
      copy: sceneCopy({ eyebrow: "M7 · 4 of 8", title: "Assemble right-ventricular evidence", objective: "Combine frontal direction, precordial balance, and mimic checks.", openingTutorMessage: "Do not stop at V1. Check axis, QRS width, terminal morphology, and the rest of the chest leads.", setup: ["A dominant R in V1 can reflect rightward ventricular forces, but it can also appear with right-bundle delay, posterior forces, pre-excitation, lead placement, or normal variation."], mechanismNarration: ["An RVH-compatible ECG pattern becomes stronger when right-axis evidence, the V1 R/S balance, persistent rightward precordial force, and a compatible clinical or diagnostic statement agree."], clinicalConnectionHeading: "Main force or terminal force?", clinicalConnectionBody: "A multi-domain pattern carries more weight than one tall R in V1.", transitionIntoTask: "Estimate axis, measure V1 R/S, trace progression, and box a conduction mimic.", completionBody: "Axis, precordial balance, QRS context, and a mimic check now support the strongest defensible pattern." }),
      layout: responsiveLayout("Full tracing plus an ordered evidence board; selecting a cell magnifies the required lead pair. Mobile uses a pinned lead mini-map and ordered checklist."),
      tutor: tutorContract({ socratic: "Does the rightward appearance begin with the dominant ventricular force, or is it a late terminal force from delayed conduction?", hints: ["RBBB is a terminal-force pattern; compare V1 with I or V6.", "RVH support should persist across independent evidence domains, not repeat the same V1 clue."], returnPrompt: "Back to [case]: complete the QRS-duration and terminal-force check before naming the chamber pattern." }),
      caseContract: caseSpec({ selectorLessonId: "hypertrophy", requestedConcept: "right_ventricular_hypertrophy", minimumTier: "A", requiredEvidence: ["Compatible RVH statement", "Axis support", "V1 R/S balance", "Precordial trend", "QRS duration and terminal morphology"], requiredLeads: ["I", "aVF", "V1", "V2", "V5", "V6"], allowedUses: ["measurement", "scored_recognition", "transfer"], fallback: "lock_scene", forbiddenClaims: ["RVH from tall R in V1 alone", "Posterior infarction without M9 evidence"] }),
      interactions: s3Interactions, minimumScore: 0.87,
      connections: { recallFrom: "M2 axis and M5 RBBB terminal force", changesNow: "Rightward chamber evidence is separated from late conduction force", reuseNext: "M7 transfer and M9 posterior mimic", clinicalUse: "Prevents tall-R-in-V1 overcalls" },
      handoffs: [handoff("train", "Train · RVH versus RBBB", "right_ventricular_hypertrophy", "discriminate", "faded")],
    }),
    buildScene({
      id: "m07-s4", partId: "m07-part-3", minutes: 7,
      source: sources("M7-S4", ["SPEC-ONTOLOGY", "SPEC-GUIDED-MINIMUM", "ARCH-M7", "V2-CHAMBERS"]),
      copy: sceneCopy({ eyebrow: "M7 · 5 of 8", title: "The precordial sweep, revisited", objective: "Measure R/S balance across V1–V6 and describe transition without forcing disease.", openingTutorMessage: "Measure the same beat component from the same baseline in every chest lead.", setup: ["Across the chest leads, the balance of ventricular forces usually shifts: R tends to grow, S tends to shrink, and transition is the lead where R first becomes larger than S."], mechanismNarration: ["The exact transition varies with rotation, anatomy, and placement. Your first job is a reproducible description: where the balance changes and whether the sequence is smooth, early, late, or not assessable.", "R amplitude · S amplitude · R/S ratio · First R > S · Early transition · Expected-range transition · Late/poor progression · Nonmonotonic · Lead sequence suspect."], clinicalConnectionHeading: "Description before etiology", clinicalConnectionBody: "Transition variation is common; an impossible jump should prompt a lead-identity or placement check.", transitionIntoTask: "Build V1→V6, trace the ratios, and mark the first R>S lead.", completionBody: "Transition and progression are now a reproducible six-lead description." }),
      layout: responsiveLayout("V1–V6 appear as a horizontal scrub rail with a synchronized R/S chart. Mobile shows one lead at a time with six persistent bar slots."),
      tutor: tutorContract({ socratic: "Where does R first become larger than S, and does the path to that point make anatomical sense?", hints: ["Transition is defined by the R/S balance, not by the tallest R in the tracing.", "A sudden impossible jump should trigger a lead identity or placement check before a disease label."], returnPrompt: "Back to [case], [lead]: enter R and S before moving to the next chest lead." }),
      caseContract: caseSpec({ selectorLessonId: "lead-territories", requestedConcept: "r_wave_progression", minimumTier: "A", requiredEvidence: ["Calibrated V1–V6", "Matched gain", "Validated lead order", "Lead-level R/S amplitudes", "Placement/order trap"], requiredLeads: ["V1", "V2", "V3", "V4", "V5", "V6"], allowedUses: ["measurement", "scored_recognition"], fallback: "lock_scene", forbiddenClaims: ["Infarction from progression alone"] }),
      interactions: s4Interactions, minimumScore: 0.85,
      connections: { recallFrom: "M2 precordial lead geometry", changesNow: "The qualitative sweep becomes a six-lead measured sequence", reuseNext: "Poor-progression differential and M9 Q-wave context", clinicalUse: "Produces a reproducible progression statement" },
      handoffs: [handoff("train", "Train · Transition and rotation", "r_wave_progression", "measure", "faded")],
    }),
    buildScene({
      id: "m07-s5", partId: "m07-part-3", minutes: 8,
      source: sources("M7-S5", ["SPEC-ISCHEMIA-ELIGIBILITY", "SPEC-CHAMBER-ELIGIBILITY", "ARCH-M7", "INV-R-ISCH"]),
      copy: sceneCopy({ eyebrow: "M7 · 6 of 8", title: "Poor progression is a finding, not a final diagnosis", objective: "Use placement, prior, conduction, chamber, and infarction evidence in the right order.", openingTutorMessage: "Describe first. Then test the cheapest reversible explanation: calibration, identity, and placement.", setup: ["Reduced or delayed R-wave growth has a broad differential: chest-lead placement, normal rotation or body habitus, altered conduction, chamber-force patterns, and prior infarction can all contribute."], mechanismNarration: ["Begin with calibration and lead sequence, describe progression, compare QRS morphology and any prior, then decide what remains plausible. Do not award infarction from progression alone.", "Acquisition/placement · Normal variation/rotation · Conduction · Chamber-force pattern · Prior infarction possible · Insufficient evidence."], clinicalConnectionHeading: "Verify before assigning cause", clinicalConnectionBody: "A valid prior needs matching identity, lead order, gain, and interpretable signal.", transitionIntoTask: "Trace progression, validate acquisition/comparison, then place the differential.", completionBody: "Poor progression is described and its strongest explanation is limited by direct evidence." }),
      layout: responsiveLayout("Current and prior/reacquisition stack at identical scale with Ghost overlay and Lead placement map. Mobile stacks matched leads and pins Same scale or Comparison invalid."),
      tutor: tutorContract({ socratic: "Which alternative would change immediately after correct lead placement, and which requires independent infarction evidence?", hints: ["Compare the whole QRS shape, not only R height.", "A valid prior needs the same lead identity, order, gain, and interpretable signal."], returnPrompt: "Back to [case]: finish the acquisition check before moving to disease hypotheses." }),
      caseContract: caseSpec({ selectorLessonId: "lead-territories", requestedConcept: "poor_r_wave_progression", minimumTier: "A", requiredEvidence: ["V1–V6 R/S sequence", "Calibration and placement", "Conduction/chamber context", "Comparable prior when used", "Territorial evidence for infarction possibility"], requiredLeads: ["V1", "V2", "V3", "V4", "V5", "V6"], allowedUses: ["scored_recognition", "transfer"], fallback: "lock_scene", forbiddenClaims: ["Acute infarction from poor progression", "Temporal change from invalid prior"] }),
      interactions: s5Interactions, minimumScore: 0.86,
      connections: { recallFrom: "M2 placement, M5 conduction, and M7-S4 progression", changesNow: "Progression opens a rule-based differential rather than a diagnosis", reuseNext: "M9 Q waves and comparison validity", clinicalUse: "Prevents machine-read anterior-infarct overcall" },
      handoffs: [handoff("train", "Train · Poor-progression differential", "poor_r_wave_progression", "discriminate", "faded"), handoff("clinical", "Clinical · Old or new", "ecg_comparison", "apply_in_context", "guided")],
    }),
    buildScene({
      id: "m07-s6", partId: "m07-part-4", minutes: 7,
      source: sources("M7-S6", ["ARCH-M7", "SPEC-CHAMBER-ELIGIBILITY", "SPEC-ISCHEMIA-ELIGIBILITY", "INV-R-CHAMBER", "INV-R-ISCH"]),
      copy: sceneCopy({ eyebrow: "M7 · 7 of 8", title: "Chamber forces can alter ST–T", objective: "Link the dominant QRS to secondary recovery, then preserve room for a primary process.", openingTutorMessage: "Read depolarization first, recovery second, then compare their directions.", setup: ["When ventricular forces are enlarged or activation is altered, recovery can shift in the opposite direction. An LVH ‘strain’ pattern describes secondary, usually discordant ST depression and T-wave inversion in leads with large dominant leftward QRS forces."], mechanismNarration: ["It strengthens an LVH pattern; it does not make every ST–T change expected, and it does not exclude a superimposed primary process."], clinicalConnectionHeading: "Context, not exclusion", clinicalConnectionBody: "Mark what the activation pattern explains and preserve unexplained change for M8/M9 assessment.", transitionIntoTask: "Mark QRS, ST, and T directions, then box the outlier.", completionBody: "Secondary-compatible recovery and an unexplained outlier are separated without an ischemia label." }),
      layout: responsiveLayout("Each lead has QRS direction and ST/T direction lanes; a causal component-removal model is available only for authored simulation. Mobile uses paired direction cards."),
      tutor: tutorContract({ socratic: "Does the ST–T vector oppose the lead’s large dominant QRS, and is the distribution explained by the same activation pattern?", hints: ["Use the dominant QRS, not a small notch, as depolarization direction.", "Secondary discordance is an expectation with limits, not permission to ignore an outlier."], returnPrompt: "Back to [lead]: mark QRS direction before deciding whether recovery is secondary." }),
      caseContract: caseSpec({ selectorLessonId: "hypertrophy", requestedConcept: "lvh_strain_pattern", minimumTier: "A", requiredEvidence: ["LVH-compatible voltage or conduction context", "Lead-specific QRS polarity", "Lead-level ST/T features", "Superimposed outlier ROI"], requiredLeads: ["I", "aVL", "V5", "V6", "V1"], allowedUses: ["mechanism", "transfer"], fallback: "authored_simulation", forbiddenClaims: ["Ischemia diagnosed or excluded", "All ST-T change dismissed as expected"] }),
      interactions: s6Interactions, minimumScore: 0.88,
      connections: { recallFrom: "M5 secondary discordance and M7 LVH bundle", changesNow: "Chamber-force recovery is compared lead by lead with activation", reuseNext: "M8 primary/secondary and M9 mimic lab", clinicalUse: "Avoids both strain overcall and ischemia dismissal" },
      handoffs: [handoff("train", "Train · Primary versus secondary recovery", "secondary_repolarization", "discriminate", "faded")],
    }),
    buildScene({
      id: "m07-s7", partId: "m07-part-4", minutes: 10,
      source: sources("M7-S7", ["SPEC-CHAMBER-ELIGIBILITY", "ARCH-M7", "SPEC-MASTERY", "ARCH-MODE-HANDOFF"]),
      copy: sceneCopy({ eyebrow: "M7 · 8 of 8", title: "Chamber-pattern transfer", objective: "Interpret unannounced chamber and progression patterns with calibrated confidence.", openingTutorMessage: "I’ll remain collapsed for the independent set. Ask if you want help; the case will pause and assistance will be recorded.", setup: ["Use an evidence bundle in the same order every time: calibration and quality → atrial morphology → frontal axis → ventricular voltage → QRS duration and morphology → R-wave progression → ST–T relationship → corroboration and limits → strongest defensible synthesis."], mechanismNarration: ["Five cases include atrial, LVH-compatible, RVH-compatible, mimic, and intentionally evidence-limited patterns."], clinicalConnectionHeading: "Strongest claim, weakest link", clinicalConnectionBody: "A weak isolated criterion does not receive the same language as a coherent multi-lead pattern.", transitionIntoTask: "Mark the two most diagnostic regions, measure, corroborate, limit, and synthesize.", completionHeading: "Module complete", completionBody: "You can now describe atrial and ventricular chamber evidence, measure voltage and R-wave progression, recognize common mimics, connect chamber forces to secondary ST–T change, and stop when the evidence stops." }),
      layout: responsiveLayout("Full 12-lead with a nine-step evidence rail and case counter; Luna is collapsed. Mobile uses a collapsible Evidence [n] of 9 block."),
      tutor: tutorContract({ socratic: "Which evidence domain is still missing from your chamber claim?", hints: ["A chamber label needs more than one version of the same voltage clue.", "Before using poor progression, audit placement and conduction."], tangentBridge: "Your viewport, annotations, draft, timer, and state are frozen.", returnPrompt: "Back to case [n], with your lead, zoom, marks, and draft intact." }),
      caseContract: caseSpec({ selectorLessonId: "hypertrophy", requestedConcept: "chamber_pattern_mixed", minimumTier: "A", requiredEvidence: ["Contract-valid atrial, LVH, RVH, mimic, and limited cases", "Calibration", "Two diagnostic regions", "Relevant measurement", "Confidence ceiling"], requiredLeads: ["I", "II", "aVF", "aVL", "V1", "V3", "V5", "V6"], allowedUses: ["measurement", "scored_recognition", "transfer"], fallback: "lock_scene", forbiddenClaims: ["Chamber diagnosis from one weak feature", "Infarction from poor progression", "Acute or treatment claim"] }),
      interactions: s7Interactions, minimumScore: 0.82,
      connections: { recallFrom: "All M7 evidence bundles", changesNow: "Targets are unannounced and evidence, synthesis, and confidence are graded separately", reuseNext: "M8 repolarization and M9 ischemia mimics", clinicalUse: "A concise evidence-limited chamber/progression read" },
      handoffs: [handoff("train", "Train · Your weakest chamber contrast", "chamber_pattern_mixed", "discriminate", "independent"), handoff("rapid", "Rapid · Mixed whole-ECG reads", "chamber_pattern_mixed", "synthesize", "independent"), handoff("clinical", "Clinical · Pre-op or chronic-disease review", "chamber_chronic_context", "apply_in_context", "faded")],
    }),
  ],
};

export default M07_CHAMBERS_VOLTAGE_MODULE;
