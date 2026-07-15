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
      "Tab follows the visual task. Arrow keys move a selected marker by one small box and Shift+Arrow by five; Enter anchors. Dragging always has a select, step, and confirm alternative.",
    summary,
    reducedMotion,
  });

const s0Feedback = feedback({
  correct: "Anchored. You identified [boundaries] and represented uncertainty where the waveform does not support a single point.",
  partial: "Your baseline is defensible. The J point remains unmarked, so ST displacement cannot yet be interpreted.",
  incorrect: "That marker is at the T-wave peak, not T end. Follow the terminal limb back to baseline.",
  unsafe: "A boundary exercise cannot support an ischemia, electrolyte, or drug diagnosis. Complete the measurement anchors first.",
  notAssessable: "Correct when a boundary is fused or obscured. The core readable beats still require their available boundaries to be marked.",
  evidenceCue: "Name QRS onset, J point, TP reference, and T end; use a range when needed.",
});

const s0Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m08-s0-anchors",
    kind: "point",
    prompt: "Place QRS onset, J point, TP reference, and T-wave end.",
    instructions: "Mark the four anchors on each beat before assigning precision or uncertainty.",
    subskills: ["localize", "measure"],
    feedback: s0Feedback,
    accessibility: access(
      "Choose the boundary name, select its time from the structured beat row, and confirm.",
      "Each beat is announced in time order as QRS onset, J point, TP reference, and T end, including uncertainty status.",
    ),
    concept: "repolarization_boundaries",
    gradePrompt: "Mark the requested recovery boundary on the selected beat.",
    allowedLeads: ["II", "V2", "V5", "V6"],
  }),
  compactInteraction({
    id: "m08-s0-boundary-range",
    kind: "region",
    prompt: "Shade the uncertainty interval when a single T-end point is not defensible.",
    instructions: "Use a bounded range on the noisy or fused T/U example; do not force false precision.",
    subskills: ["measure", "calibrate_confidence"],
    feedback: s0Feedback,
    accessibility: access(
      "Enter earliest and latest defensible T-end times with millisecond steppers.",
      "The uncertainty interval and the reason a point estimate is unavailable are announced.",
    ),
    concept: "t_end_uncertainty_range",
    allowedLeads: ["II", "V5", "V6"],
    minimumDurationMs: 20,
  }),
];

const s1Feedback = feedback({
  correct: "Correct. [Activation pattern] explains [secondary-compatible leads], while [outlier] is not explained and remains a separate recovery finding.",
  partial: "Your T direction is right. QRS width and dominant direction are still missing, so primary versus secondary remains unproven.",
  incorrect: "This ST–T direction is opposite a clearly abnormal dominant QRS and follows its lead distribution. Reconsider a secondary-compatible relationship.",
  unsafe: "Do not turn ‘not secondary’ into an acute diagnosis. This packet supports a recovery relationship, not etiology or treatment.",
  notAssessable: "Correctly limited when a baseline or lead is unreadable. Readable QRS and T directions must still be compared.",
  evidenceCue: "QRS width and direction come before ST/T direction and distribution.",
});

const s1Interactions: LearningInteraction[] = [
  compactInteraction({
    id: "m08-s1-qrs-width",
    kind: "caliper",
    prompt: "Measure QRS before classifying recovery.",
    instructions: "Place onset/end calipers and label both boundaries.",
    subskills: ["measure", "discriminate"],
    feedback: s1Feedback,
    accessibility: access("Use QRS onset/end steppers in the selected lead.", "QRS duration and activation-context status are announced."),
    measurement: "qrs",
    target: { source: "packet_measurement", measurementKey: "qrs_duration_ms", toleranceMs: 20 },
    requireBoundaryLabels: true,
  }),
  compactInteraction({
    id: "m08-s1-direction-pairing",
    kind: "pairing",
    prompt: "Pair dominant QRS direction with ST/T direction in three leads.",
    instructions: "Classify the relationship only after both components are marked.",
    subskills: ["discriminate", "explain_mechanism"],
    feedback: s1Feedback,
    accessibility: access("Use positive, negative, or unclear text selectors for QRS and recovery.", "Each lead is announced as activation direction, recovery direction, and relation."),
    left: [
      { id: "v1-qrs", label: "V1 dominant QRS" },
      { id: "i-qrs", label: "I dominant QRS" },
      { id: "v6-qrs", label: "V6 dominant QRS" },
    ],
    right: [
      { id: "v1-stt", label: "V1 ST/T direction" },
      { id: "i-stt", label: "I ST/T direction" },
      { id: "v6-stt", label: "V6 ST/T direction" },
    ],
    correctPairs: { "v1-qrs": "v1-stt", "i-qrs": "i-stt", "v6-qrs": "v6-stt" },
  }),
  compactInteraction({
    id: "m08-s1-outlier",
    kind: "region",
    prompt: "Box the recovery region not explained by the activation pattern.",
    instructions: "Mark the superimposed outlier and preserve it for separate assessment.",
    subskills: ["localize", "calibrate_confidence"],
    feedback: s1Feedback,
    accessibility: access("Select the outlier lead and named ST/T segment from the region list.", "The outlier lead, interval, and evidence limit are announced."),
    concept: "primary_or_superimposed_repolarization_outlier",
    allowedLeads: ["I", "aVL", "V1", "V5", "V6"],
    minimumDurationMs: 40,
  }),
];

const s2Feedback = feedback({
  correct: "Reproducible description: ‘[direction/morphology] in [lead set], [distribution], with [QRS context] and [uncertainty].’ You named the finding without inventing a cause.",
  partial: "You marked the correct leads. Add the baseline-relative direction and T-wave shape so another reader can reconstruct the finding.",
  incorrect: "The selected segment is [relative direction] to the marked baseline. Recheck the reference before naming the displacement.",
  unsafe: "The word ‘[acute/ischemic/electrolyte]’ is not supported in this scene. Replace it with a lead-level ST–T description.",
  notAssessable: "Correct when magnitude or morphology is unreliable because of quality or calibration. Direction and distribution may still be assessable.",
  evidenceCue: "Reference, lead set, direction, morphology, QRS context, and uncertainty are separate fields.",
});

const s2Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s2-baseline-j", kind: "point", prompt: "Mark the baseline and J point before describing ST.", instructions: "Place both anchors in the selected lead.", subskills: ["localize", "measure"], feedback: s2Feedback, accessibility: access("Choose TP reference and J point from the landmark list.", "Baseline and J-point coordinates are announced."), concept: "baseline_and_j_point", gradePrompt: "Mark the reference and QRS-to-ST junction.", allowedLeads: ["II", "V2", "V4", "V5", "V6"] }),
  compactInteraction({ id: "m08-s2-stt-region", kind: "region", prompt: "Mark the ST segment and T wave whose morphology you will describe.", instructions: "Draw separate regions for ST and T; confirm shape and polarity.", subskills: ["localize", "recognize"], feedback: s2Feedback, accessibility: access("Select ST segment and T wave from named beat regions.", "Selected ST direction/slope and T polarity/shape are announced."), concept: "st_t_morphology", allowedLeads: ["I", "II", "III", "aVL", "aVF", "V2", "V3", "V4", "V5", "V6"], minimumDurationMs: 40 }),
  compactInteraction({ id: "m08-s2-distribution", kind: "lead_select", prompt: "Paint the affected lead distribution.", instructions: "Select every lead containing the marked morphology; reject unrelated leads.", subskills: ["localize", "discriminate"], feedback: s2Feedback, accessibility: access("Use the anatomical lead checklist rather than painting.", "Affected leads are announced in anatomical groups."), selectionMode: "multiple", correctLeads: ["V4", "V5", "V6"], allowedLeads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"], rejectExtraSelections: true }),
  compactInteraction({ id: "m08-s2-sentence", kind: "free_response", prompt: "Build one lead-level recovery sentence.", instructions: "Name reference, distribution, direction, morphology, QRS context, and uncertainty; do not name etiology.", subskills: ["synthesize", "calibrate_confidence"], feedback: s2Feedback, accessibility: access("Type or dictate from the structured sentence frame.", "The response is checked for reconstructable lead-level description and absence of unsupported etiology."), responseLabel: "ST–T description", placeholder: "Relative to …, there is … in … with … and …", minimumCharacters: 40, sentenceFrame: "Relative to [reference], there is [direction/morphology] in [lead set], with [QRS context] and [uncertainty].", rubric: [
    { id: "reference", label: "Names the reference", acceptedConcepts: ["tp_baseline", "defensible_baseline"], required: true },
    { id: "distribution", label: "Names the lead set", acceptedConcepts: ["lead_distribution"], required: true },
    { id: "morphology", label: "Names ST and/or T morphology", acceptedConcepts: ["st_elevation", "st_depression", "t_wave_inversion", "biphasic_t", "nonspecific_st_t_change"], required: true },
    { id: "context", label: "Names QRS context or uncertainty", acceptedConcepts: ["narrow_qrs", "wide_qrs", "secondary_repolarization", "uncertain_baseline"], required: true },
  ] }),
];

const s3Feedback = feedback({
  correct: "Reproducible. QT is [value/range] ms in [lead] by the [method], measured across [beats], with [uncertainty].",
  partial: "Beat 1 is within tolerance. Measure a second eligible beat and document the lead before the QT can complete.",
  incorrect: "Your right caliper includes a separate U wave. Mark T end at [accepted region] and label U separately.",
  unsafe: "A QT measurement alone does not establish drug causation, torsades, or a treatment plan. Complete the interval and context first.",
  notAssessable: "Correct when T end is fused or obscured in the chosen lead. A validated alternate lead must still be used when available.",
  evidenceCue: "Choose a clear lead, use one named method on two beats, and keep U separate.",
});

const s3Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s3-qt-calipers", kind: "caliper", prompt: "Measure QT on two eligible beats.", instructions: "Use the selected lead and one named T-end method; document lead and uncertainty.", subskills: ["measure", "calibrate_confidence"], feedback: s3Feedback, accessibility: access("Set QRS onset and T end with millisecond steppers for Beat 1 and Beat 2.", "Lead, method, beat values, mean QT, and uncertainty are announced."), measurement: "qt", target: { source: "packet_measurement", measurementKey: "qt_interval_ms", toleranceMs: 25 }, requireBoundaryLabels: true }),
  compactInteraction({ id: "m08-s3-u-wave", kind: "region", prompt: "Mark the U wave separately when present.", instructions: "Box the post-T deflection without extending the QT caliper through it.", subskills: ["localize", "discriminate"], feedback: s3Feedback, accessibility: access("Choose T end and U onset from the structured landmark list.", "T terminal limb, T end, and separate U-wave region are announced."), concept: "u_wave_separate_from_t", allowedLeads: ["II", "V2", "V3", "V5", "V6"], minimumDurationMs: 20 }),
];

const s4Feedback = feedback({
  correct: "Correct. Keep the result beside the supplied QT of 360 ms and RR of 640 ms, name the formula, and compare both corrections before interpreting their divergence.",
  partial: "Your calculation is close. Recheck the exponent and keep QT and RR in seconds until the final conversion to milliseconds.",
  incorrect: "The formula received milliseconds where seconds were required. Convert QT and RR to seconds, then recalculate.",
  unsafe: "Do not choose a treatment or torsades-risk category from an unreviewed threshold. Report the measurement, method, rate, and uncertainty.",
  notAssessable: "Correct when QT, RR, or formula source is missing. With all inputs present, calculate both estimates even if risk category remains unavailable.",
  evidenceCue: "Convert to seconds, calculate both formulas, and state rate/formula dependence.",
});

const s4Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s4-bazett", kind: "numeric_entry", prompt: "Given QT 360 ms (0.360 s) and RR 640 ms (0.640 s), calculate Bazett QTc: QT ÷ √RR.", instructions: "Use seconds inside the formula and enter only the final QTc in milliseconds.", subskills: ["measure", "explain_mechanism"], feedback: s4Feedback, accessibility: access("The fixed inputs are QT 0.360 seconds and RR 0.640 seconds; enter the Bazett result in milliseconds.", "Bazett inputs, units, calculation, result, and rounding are announced."), label: "Bazett QTc", unit: "ms", target: { source: "authored_simulation", value: 450, tolerance: 5 }, minimum: 200, maximum: 900 }),
  compactInteraction({ id: "m08-s4-fridericia", kind: "numeric_entry", prompt: "Using the same QT 360 ms and RR 640 ms, calculate Fridericia QTc: QT ÷ ∛RR.", instructions: "Use 0.360 and 0.640 seconds inside the formula; enter the final QTc in milliseconds.", subskills: ["measure", "explain_mechanism"], feedback: s4Feedback, accessibility: access("The fixed inputs are QT 0.360 seconds and RR 0.640 seconds; enter the Fridericia result in milliseconds.", "Fridericia inputs, calculation, result, and divergence from Bazett are announced."), label: "Fridericia QTc", unit: "ms", target: { source: "authored_simulation", value: 418, tolerance: 5 }, minimum: 200, maximum: 900 }),
  compactInteraction({ id: "m08-s4-rate-model", kind: "model_explore", prompt: "Inspect how the two corrections diverge at rate extremes.", instructions: "Visit slow, mid-range, and fast frames and compare raw QT, QTcB, and QTcF.", subskills: ["explain_mechanism", "calibrate_confidence"], feedback: s4Feedback, accessibility: access("Use Slow, Mid-range, and Fast buttons plus the accessible data table.", "Each frame announces rate, RR, raw QT, QTcB, QTcF, and divergence."), model: "repolarization", frames: [
    { id: "slow", label: "Slower rate", narration: "QT and RR lengthen; correction models diverge.", waveformLabel: "Slow-rate comparison" },
    { id: "mid", label: "Mid-range rate", narration: "Correction estimates are often closer in this teaching range.", waveformLabel: "Mid-rate comparison" },
    { id: "fast", label: "Faster rate", narration: "RR shortens and formula behavior diverges again.", waveformLabel: "Fast-rate comparison" },
  ], requiredFrameIds: ["slow", "mid", "fast"] }),
];

const s5Feedback = feedback({
  correct: "Correct. QT is [value], but QRS contributes [value]. The wide-QRS/pacing confound must be reported; a reviewed method is needed before a recovery-risk conclusion.",
  partial: "QT is measured. Add QRS duration and the remaining JT component before interpreting the total.",
  incorrect: "The longer QT here is explained largely by wider depolarization while the model’s recovery component is unchanged.",
  unsafe: "A narrow-QRS QTc threshold cannot be applied silently here, and this scene does not support a drug stop/start decision.",
  notAssessable: "Correct when no reviewed wide-QRS method is configured. Raw QRS, QT, and the confound remain assessable.",
  evidenceCue: "Split QT into QRS and JT; report the confound before any adjusted interpretation.",
});

const s5Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s5-qrs", kind: "caliper", prompt: "Measure the QRS component of QT.", instructions: "Mark QRS onset and J point.", subskills: ["measure"], feedback: s5Feedback, accessibility: access("Set QRS onset and J point with millisecond steppers.", "QRS duration is announced as the depolarization component."), measurement: "qrs", target: { source: "packet_measurement", measurementKey: "qrs_duration_ms", toleranceMs: 20 }, requireBoundaryLabels: true }),
  compactInteraction({ id: "m08-s5-qt", kind: "caliper", prompt: "Measure total QT on the same beat.", instructions: "Mark QRS onset and T end without changing the lead or beat.", subskills: ["measure"], feedback: s5Feedback, accessibility: access("Set QT boundaries on the same structured beat row.", "Total QT and its shared QRS onset are announced."), measurement: "qt", target: { source: "packet_measurement", measurementKey: "qt_interval_ms", toleranceMs: 25 }, requireBoundaryLabels: true }),
  compactInteraction({ id: "m08-s5-jt", kind: "numeric_entry", prompt: "Derive JT by subtracting QRS from QT.", instructions: "Enter the remaining recovery component and state whether a reviewed wide-QRS method is available.", subskills: ["measure", "calibrate_confidence"], feedback: s5Feedback, accessibility: access("Use the text equation QT minus QRS equals JT.", "QT, QRS, derived JT, and policy availability are announced."), label: "JT interval", unit: "ms", target: { source: "packet_measurement", measurementKey: "jt_interval_ms", tolerance: 5 }, minimum: 100, maximum: 700 }),
];

const s6Feedback = feedback({
  correct: "Complete chain. You verified [QT/QTc/method/rate/QRS], reconciled [available factors], requested [missing data], and stayed within the reviewed follow-up category.",
  partial: "Your QTc is supported. The workflow remains incomplete until you check [QRS/prior/electrolytes/interactions].",
  incorrect: "The machine value cannot replace your manual boundary and formula check. Return to the ECG before using the medication context.",
  unsafe: "A stop/start/dose order is not authorized by this storyboard. Use the reviewed educational category or request supervision/local-pathway review.",
  notAssessable: "Correct when a required datum or policy is absent. Manual QT/QTc and QRS assessment must still be completed when available.",
  evidenceCue: "Verify ECG first; then reconcile medicines, clearance, electrolytes, symptoms, prior, and reviewed follow-up.",
});

const s6Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s6-workflow-order", kind: "sequence", prompt: "Order the medication-QT evidence chain.", instructions: "Place ECG verification before medication/context and reviewed follow-up.", subskills: ["synthesize", "apply_in_context"], feedback: s6Feedback, accessibility: access("Use Move earlier/later controls on the eight workflow steps.", "The complete ordered medication-QT workflow is announced."), cards: [
    { id: "verify", label: "1 Verify ECG" }, { id: "manual", label: "2 Manual QT/QTc" }, { id: "qrs", label: "3 QRS confound" }, { id: "meds", label: "4 Reconcile medicines" }, { id: "interactions", label: "5 Check interactions/clearance" }, { id: "labs", label: "6 Check electrolytes/symptoms" }, { id: "prior", label: "7 Compare prior" }, { id: "followup", label: "8 Reviewed follow-up category" },
  ], correctOrder: ["verify", "manual", "qrs", "meds", "interactions", "labs", "prior", "followup"] }),
  compactInteraction({ id: "m08-s6-clinical-stages", kind: "clinical_stage", prompt: "Complete the staged medication-QT review.", instructions: "Measure before reveal; choose data requests and only a reviewed educational category.", subskills: ["measure", "apply_in_context", "calibrate_confidence"], feedback: s6Feedback, accessibility: access("Open authored context stages with buttons; medicine data is text, never icon-only.", "Each reveal announces its authored source and the remaining missing data."), stages: [
    { id: "ecg", heading: "Verify ECG", revealCopy: "Full ECG, rate, QRS, and manual QT workspace are available; machine QTc remains hidden.", question: "What must be completed before medication context?", options: [
      { id: "manual-first", label: "Manual QT/QTc and QRS context", rationale: "Required waveform evidence." },
      { id: "machine-only", label: "Use the hidden machine label", rationale: "Cannot replace manual verification." },
    ], acceptableOptionIds: ["manual-first"] },
    { id: "context", heading: "Reconcile context", revealCopy: "Authored medication timing, dose class, clearance, symptoms, and available labs are revealed.", question: "Which next data are still required?", options: [
      { id: "missing-data", label: "Obtain the packet’s missing interactions, electrolytes, or prior", rationale: "Completes the evidence chain." },
      { id: "guess", label: "Infer the missing values", rationale: "Unsupported." },
    ], acceptableOptionIds: ["missing-data"] },
    { id: "action", heading: "Reviewed follow-up", revealCopy: "The action layer is enabled only when clinicalReviewStatus is approved.", question: "What response is authorized?", options: [
      { id: "reviewed-category", label: "Use the enabled reviewed follow-up category", rationale: "Stays within policy." },
      { id: "specific-order", label: "Create a stop/start/dose order", rationale: "Not authorized by this scene." },
    ], acceptableOptionIds: ["reviewed-category"], unsafeOptionIds: ["specific-order"] },
  ] }),
];

const s7Feedback = feedback({
  correct: "Correct. The model links [ion change] to [components], while the comparison shows overlap with [mimic]. The defensible next step is to obtain [datum], not infer a laboratory value.",
  partial: "You identified the T-wave change. Inspect [P/QRS/ST/QT] before deciding how broad the pattern is.",
  incorrect: "That component did not change when only [ion] moved. Reset, compare before/after, and mark the actual regions.",
  unsafe: "The waveform does not supply a numeric electrolyte level or a patient-specific replacement/treatment order. State the compatible pattern and confirming datum.",
  notAssessable: "Correct that a specific electrolyte cause is not assessable from an overlapping pattern. The changed waveform components remain assessable.",
  evidenceCue: "Track P, PR, QRS, ST/T, and QT separately; then request laboratory confirmation.",
});

const s7Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s7-ion-model", kind: "model_explore", prompt: "Change one ion teaching state and mark what moves.", instructions: "Visit potassium and calcium frames; magnesium remains a context card rather than a unique waveform generator.", subskills: ["explain_mechanism", "recognize"], feedback: s7Feedback, accessibility: access("Use named Low/reference/high teaching-state buttons and component tables.", "Each model frame announces changed P, PR, QRS, ST, T, and QT components and states that values are not patient labs."), model: "repolarization", frames: [
    { id: "k", label: "Extracellular K — teaching continuum", narration: "Track T-wave and conduction components without inferring a serum value.", waveformLabel: "Pattern overlap" },
    { id: "ca", label: "Extracellular Ca — teaching continuum", narration: "Track ST duration and QT without inferring a serum value.", waveformLabel: "Pattern overlap" },
    { id: "mg", label: "Mg context — no unique waveform slider", narration: "Magnesium matters to repolarization risk but lacks a unique graded surface pattern here.", waveformLabel: "Request laboratory confirmation" },
  ], requiredFrameIds: ["k", "ca", "mg"] }),
  compactInteraction({ id: "m08-s7-component-map", kind: "categorize", prompt: "Assign the changed components and the confirming datum.", instructions: "Classify model observations separately from real-case cause confirmation.", subskills: ["discriminate", "apply_in_context"], feedback: s7Feedback, accessibility: access("Use a component-by-cause table with explicit overlap labels.", "Changed components, overlapping mimics, and needed lab or medication data are announced."), items: [
    { id: "t-qrs", label: "T-wave and QRS pattern change" },
    { id: "st-qt", label: "ST duration and QT change" },
    { id: "lab", label: "Measured electrolyte value" },
    { id: "meds", label: "Medication and prior context" },
  ], categories: [
    { id: "k-hypothesis", label: "Potassium-compatible hypothesis" },
    { id: "ca-hypothesis", label: "Calcium-compatible hypothesis" },
    { id: "confirmation", label: "Required confirmation/context" },
  ], correctCategoryByItem: { "t-qrs": "k-hypothesis", "st-qt": "ca-hypothesis", lab: "confirmation", meds: "confirmation" } }),
];

const s8Feedback = feedback({
  correct: "Well compared. [Pattern] is more compatible with [category] because [two independent discriminators]. [Overlap/uncertainty] remains, so context or serial evidence is still needed.",
  partial: "The distribution is correct. Add one independent discriminator—QRS context, reciprocal evidence, PR/baseline finding, or valid prior—before ranking.",
  incorrect: "That ranking relies on one morphology while [contradictory discriminator] is visible. Reopen the matching lead row.",
  unsafe: "This scene does not authorize an acute ischemia diagnosis, culprit vessel, or treatment action. Keep the output at pattern compatibility and needed evidence.",
  notAssessable: "Correct when the distinction remains unresolved because a required datum is missing. Readable discriminators must still be completed.",
  evidenceCue: "Compare distribution, QRS context, J/ST, T, PR/baseline, reciprocity, prior, and context.",
});

const s8Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s8-triad", kind: "compare", prompt: "Compare variant, pericarditis-compatible, and secondary/nonspecific patterns.", instructions: "Complete at least five discriminator rows before ranking.", subskills: ["discriminate", "calibrate_confidence"], feedback: s8Feedback, accessibility: access("Navigate a real comparison table with row and column headers.", "Each triad row is announced across all cases before any category label."), leftCaseConcept: "early_repolarization_or_variant", rightCaseConcept: "pericarditis_or_secondary_st_t", dimensions: [
    { id: "distribution", label: "Distribution", leftAnswer: "Lead pattern recorded", rightAnswer: "Lead pattern recorded" },
    { id: "qrs", label: "QRS context", leftAnswer: "Narrow/variant context", rightAnswer: "Secondary pattern when present" },
    { id: "j-st", label: "J/ST morphology", leftAnswer: "Describe", rightAnswer: "Describe" },
    { id: "pr", label: "PR/baseline evidence", leftAnswer: "Assess only if readable", rightAnswer: "Assess only if readable" },
    { id: "reciprocal", label: "Reciprocal evidence", leftAnswer: "Record presence/absence", rightAnswer: "Record presence/absence" },
    { id: "prior", label: "Prior/context", leftAnswer: "Needed when overlap remains", rightAnswer: "Needed when overlap remains" },
  ] }),
  compactInteraction({ id: "m08-s8-discriminator-region", kind: "region", prompt: "Mark an independent discriminator in the matched leads.", instructions: "Choose a region that differs between the cases rather than a shared ST shape.", subskills: ["localize", "discriminate"], feedback: s8Feedback, accessibility: access("Select the case, lead, and named segment from the comparison table.", "The selected discriminator and its status across the triad are announced."), concept: "nonischemic_st_t_discriminator", allowedLeads: ["I", "II", "III", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"], minimumDurationMs: 30 }),
];

const s9Feedback = feedback({
  correct: "Supported. Your waveform evidence shows [evidence sentence], and your conclusion—‘[normalized conclusion]’—matches the packet’s allowed claim.",
  partial: "You have [credited evidence]. [Missing boundary/context/formula] must be completed before the conclusion unlocks.",
  incorrect: "Your conclusion conflicts with [case-specific discriminator]. Reopen [lead/measurement] and rebuild from the QRS context.",
  unsafe: "This case does not support an acute diagnosis, numeric laboratory inference, drug order, or torsades claim. Return to supported recovery evidence and needed data.",
  notAssessable: "Correctly limited when a specific inference lacks its required datum or method. Readable waveform evidence must still be described.",
  evidenceCue: "QRS context → baseline/J → ST/T → QT/rate/formula → context → strongest claim.",
});

const s9Interactions: LearningInteraction[] = [
  compactInteraction({ id: "m08-s9-proof-region", kind: "region", prompt: "Mark the decisive recovery evidence on this unannounced case.", instructions: "Box the ST/T or QT-end region and identify its QRS context.", subskills: ["localize", "discriminate"], feedback: s9Feedback, accessibility: access("Choose a lead and named recovery segment; pair it with QRS context.", "The decisive region, lead, morphology, and activation context are announced."), concept: "mixed_repolarization_evidence", allowedLeads: ["I", "II", "III", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"], minimumDurationMs: 30 }),
  compactInteraction({ id: "m08-s9-synthesis", kind: "free_response", prompt: "Submit the strongest defensible recovery/QT conclusion.", instructions: "Include waveform description, method when measured, context limitation, and confidence.", subskills: ["synthesize", "calibrate_confidence"], feedback: s9Feedback, accessibility: access("Type or dictate from the structured frame; speech style is not graded.", "The response is checked for waveform evidence, method, QRS context, limitation, and confidence."), responseLabel: "Recovery synthesis", placeholder: "The ECG shows … in …; QT/QTc is … by …; however …", minimumCharacters: 50, sentenceFrame: "The ECG shows [ST/T finding and leads] with [QRS context]. QT/QTc is [value/method if relevant]. [Limit], so [conclusion/confidence].", rubric: [
    { id: "waveform", label: "Names lead-level recovery evidence", acceptedConcepts: ["st_elevation", "st_depression", "t_wave_inversion", "nonspecific_st_t_change", "secondary_repolarization"], required: true },
    { id: "method", label: "Names QT lead/method/rate/formula when relevant", acceptedConcepts: ["qt_interval", "qtc_bazett", "qtc_fridericia", "wide_qrs_confound", "not_applicable"], required: true },
    { id: "limit", label: "States missing data or evidence ceiling", acceptedConcepts: ["not_assessable", "needs_context", "needs_labs", "needs_reviewed_method"], required: true },
    { id: "confidence", label: "Calibrates confidence", acceptedConcepts: ["low_confidence", "moderate_confidence", "high_confidence"], required: true },
  ] }),
];

export const M08_REPOLARIZATION_MODULE: ProductionModule = {
  id: "repolarization-safety",
  order: 8,
  title: "Repolarization, QT, Drugs, Electrolytes, and Nonischemic ST–T",
  shortTitle: "Repolarization & QT",
  duration: "60–75 min",
  outcome: "Describe ST–T in activation context, measure and correct QT reproducibly, recognize wide-QRS limits, and perform safe drug/electrolyte information workflows.",
  prerequisiteIds: ["leads-vectors", "ventricular-conduction"],
  accent: "#A85473",
  sourceRequirementIds: ["SPEC-11.11", "SPEC-11.15", "SPEC-QT-ELIGIBILITY", "SPEC-ISCHEMIA-ELIGIBILITY", "ARCH-M8", "INV-R-QT", "INV-R-CLINREV"],
  scenes: [
    buildScene({ id: "m08-s0", partId: "m08-part-1", minutes: 6, source: sources("M8-S0", ["SPEC-11.11", "SPEC-11.15", "FOUND-ST-QT", "SPEC-VIEWER", "ARCH-M8", "INV-R-QT"]), copy: sceneCopy({ eyebrow: "M8 · 1 of 10", title: "Baseline, J point, T end", objective: "Anchor every recovery claim to defensible boundaries.", openingTutorMessage: "Name the boundary before you measure the interval.", setup: ["The J point is the end of QRS and the beginning of the ST segment. ST displacement needs a reference baseline, usually a stable TP segment when one is visible."], mechanismNarration: ["QT begins at QRS onset and ends where the T wave returns to baseline. Noise, tachycardia, atrial activity, U waves, and altered QRS morphology can make each boundary uncertain. Uncertainty belongs in the measurement—not outside it.", "QRS onset · J point · TP reference · T-wave end · Boundary uncertain."], clinicalConnectionHeading: "Measurement honesty", clinicalConnectionBody: "A bounded range is stronger than false precision when the waveform cannot support one point.", transitionIntoTask: "Place every readable anchor and shade uncertainty where needed.", completionBody: "Recovery boundaries and their uncertainty are now explicit." }), layout: responsiveLayout("A four-column boundary board shows normal, RBBB, LBBB/paced, and ambiguous beats. Mobile shows one beat with a persistent four-boundary receipt."), tutor: tutorContract({ socratic: "Where does ventricular activation end, and how certain is that transition in this QRS morphology?", hints: ["Trace the final QRS deflection until it joins the ST segment; do not use the tallest peak.", "For T end, follow the terminal downslope toward baseline and keep a visible U wave separate."], returnPrompt: "Back to [beat]: place [missing boundary], then record its uncertainty." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "repolarization_boundaries", minimumTier: "A", requiredEvidence: ["Accepted QRS onset/J/baseline/T-end intervals", "Lead identity", "QRS duration", "Ambiguity flags"], requiredLeads: ["II", "V2", "V5", "V6"], allowedUses: ["measurement", "worked_example"], fallback: "authored_simulation", forbiddenClaims: ["Etiology from boundary task", "False millisecond precision"] }), interactions: s0Interactions, minimumScore: 0.9, connections: { recallFrom: "M1 ST/T/QT anchors and M5 QRS morphology", changesNow: "Every recovery boundary carries explicit uncertainty", reuseNext: "All M8 measurements and M9 ST localization", clinicalUse: "Prevents false ST/QT measurements" }, handoffs: [handoff("train", "Train · Recovery boundaries", "repolarization_boundaries", "measure", "guided")] }),
    buildScene({ id: "m08-s1", partId: "m08-part-1", minutes: 7, source: sources("M8-S1", ["ARCH-M8", "V2-REPOLARIZATION", "SPEC-ISCHEMIA-ELIGIBILITY"]), copy: sceneCopy({ eyebrow: "M8 · 2 of 10", title: "Recovery follows its activation context", objective: "Distinguish expected secondary recovery from a primary or unexplained change.", openingTutorMessage: "QRS first. Recovery cannot be classified in isolation.", setup: ["Primary repolarization change begins in recovery itself. Secondary repolarization change follows abnormal depolarization, as with bundle delay, ventricular pacing, pre-excitation, or marked chamber-force patterns."], mechanismNarration: ["Read QRS duration, morphology, and dominant direction first. If ST–T direction and distribution fit that activation, call the relationship secondary-compatible. If they do not, preserve a primary or superimposed process for separate assessment."], clinicalConnectionHeading: "Explain what activation explains", clinicalConnectionBody: "A secondary pattern can coexist with an outlier that needs separate assessment.", transitionIntoTask: "Measure QRS, pair directions, and box the outlier.", completionBody: "Secondary-compatible recovery and primary/unexplained change are separated without an acute label." }), layout: responsiveLayout("Activation/Recovery board beside paired magnifiers; component isolation unlocks after prediction. Mobile uses paired cards under each lead."), tutor: tutorContract({ socratic: "Would this T-wave direction be surprising if the ventricular activation sequence were normal?", hints: ["Compare the dominant—not terminally tiny—QRS force with ST and T.", "A secondary pattern can coexist with an outlier that needs separate assessment."], returnPrompt: "Back to [lead]: finish QRS width and direction before classifying ST–T." }), caseContract: caseSpec({ selectorLessonId: "bundle-branch-blocks", requestedConcept: "primary_secondary_repolarization", minimumTier: "A", requiredEvidence: ["QRS duration/morphology", "Lead-specific QRS/ST/T polarity", "Activation context", "Superimposed outlier ROI"], requiredLeads: ["V1", "I", "V6"], allowedUses: ["mechanism", "scored_recognition", "transfer"], fallback: "authored_simulation", forbiddenClaims: ["Acute etiology", "All change dismissed as secondary"] }), interactions: s1Interactions, minimumScore: 0.88, connections: { recallFrom: "M5 secondary discordance and M7 strain", changesNow: "Primary versus secondary is proven from QRS/recovery relations", reuseNext: "M8 nonischemic comparisons and M9 mimics", clinicalUse: "Prevents both ischemia overcall and dismissal" }, handoffs: [handoff("train", "Train · Recovery relationship", "primary_secondary_repolarization", "discriminate", "faded")] }),
    buildScene({ id: "m08-s2", partId: "m08-part-1", minutes: 8, source: sources("M8-S2", ["SPEC-ONTOLOGY", "SPEC-GUIDED-MINIMUM", "ARCH-M8", "FOUND-ST-QT"]), copy: sceneCopy({ eyebrow: "M8 · 3 of 10", title: "Build a lead-level recovery sentence", objective: "Describe displacement, shape, polarity, distribution, and context.", openingTutorMessage: "Describe what the ink does. Cause comes later.", setup: ["ST elevation, ST depression, T-wave inversion, and nonspecific ST–T change are findings before they are diagnoses."], mechanismNarration: ["A useful description names the reference, lead set, direction, magnitude when valid, morphology, distribution, QRS context, and uncertainty. Words such as horizontal, downsloping, upsloping, symmetric, asymmetric, deep, or biphasic must point to visible waveform evidence.", "Reference · Lead set · Direction · Magnitude · ST shape · T polarity/shape · QRS context · Uncertainty."], clinicalConnectionHeading: "Reconstructable evidence", clinicalConnectionBody: "Another reader should be able to find the same feature from your sentence.", transitionIntoTask: "Anchor, mark, paint, and assemble the sentence.", completionBody: "The ST–T finding is described without invented etiology." }), layout: responsiveLayout("Full tracing above a morphology workbench with baseline ruler and tangent line. Mobile uses a full-board mini-map, selected lead, and collapsible sentence builder."), tutor: tutorContract({ socratic: "Could another reader reconstruct your finding from the lead set, direction, and morphology you named?", hints: ["Anchor ST to the baseline before choosing elevation or depression.", "T-wave polarity and shape are separate fields; mark both when visible."], returnPrompt: "Back to [lead]: complete the reference and morphology marks before assembling the sentence." }), caseContract: caseSpec({ selectorLessonId: "ischemia-st-t", requestedConcept: "st_t_morphology", minimumTier: "A", requiredEvidence: ["Baseline/J ROIs", "Lead-level ST/T morphology", "Distribution", "QRS context", "Calibration for magnitude"], requiredLeads: ["I", "II", "III", "aVL", "aVF", "V2", "V3", "V4", "V5", "V6"], allowedUses: ["measurement", "scored_recognition"], fallback: "authored_simulation", forbiddenClaims: ["Etiology before description", "Unreviewed numeric threshold"] }), interactions: s2Interactions, minimumScore: 0.86, connections: { recallFrom: "M1 baseline/J/T and M2 distribution", changesNow: "ST/T becomes a reproducible multi-field description", reuseNext: "M8 variants and all M9 ischemia reasoning", clinicalUse: "Supports precise communication without overdiagnosis" }, handoffs: [handoff("train", "Train · ST/T morphology deck", "st_t_morphology", "recognize", "faded")] }),
    buildScene({ id: "m08-s3", partId: "m08-part-2", minutes: 8, source: sources("M8-S3", ["SPEC-QT-ELIGIBILITY", "SPEC-VIEWER", "ARCH-M8", "INV-R-QT", "INV-R-PRECISION"]), copy: sceneCopy({ eyebrow: "M8 · 4 of 10", title: "QT is a measured interval, not a machine label", objective: "Select a clear lead, separate T from U, and reproduce QT across beats.", openingTutorMessage: "Choose the clearest ending before placing a caliper.", setup: ["QT runs from the earliest QRS onset to the end of ventricular repolarization represented by the T wave. Choose a lead with a clear T ending, inspect more than one beat, and document the lead."], mechanismNarration: ["The tangent method extends the steepest terminal T-wave slope to the baseline; the threshold method follows the waveform’s return to baseline. U waves are not automatically included. When the end is genuinely fused or indistinct, report a range or another lead rather than false precision.", "Tangent method · Threshold method · Use another lead · Bounded range · T/U separation uncertain."], clinicalConnectionHeading: "Verify the machine", clinicalConnectionBody: "Lead, method, beat reproducibility, and uncertainty belong beside the QT value.", transitionIntoTask: "Choose the lead, measure two beats, and separate U.", completionBody: "QT is reproducibly measured with a named lead, method, and uncertainty." }), layout: responsiveLayout("Lead carousel with synchronized median and rhythm beats plus measurement notebook. Mobile uses one magnified lead with Beat 1/Beat 2/Median selector."), tutor: tutorContract({ socratic: "What makes this deflection part of T rather than a separate U wave?", hints: ["Use the earliest QRS onset and the terminal return of T—not the T peak.", "If T and U merge, show the uncertainty instead of forcing a point."], returnPrompt: "Back to [lead], beat [n]: finish the T-end method you selected." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "qt_interval", minimumTier: "A", requiredEvidence: ["High-rate or validated median/fiducials", "QT and QTc source", "Rate/RR", "Accepted T-end interval", "Two eligible beats/leads"], requiredLeads: ["II", "V2", "V5", "V6"], allowedUses: ["measurement", "scored_recognition"], fallback: "lock_scene", forbiddenClaims: ["U-wave inclusion", "False precision", "Drug causation or torsades"] }), interactions: s3Interactions, minimumScore: 0.9, connections: { recallFrom: "M8-S0 boundaries", changesNow: "Boundary choice becomes a two-beat documented QT measurement", reuseNext: "Rate correction and medication safety", clinicalUse: "Audits machine QT/QTc" }, handoffs: [handoff("train", "Train · QT boundary calibration", "qt_interval", "measure", "faded")] }),
    buildScene({ id: "m08-s4", partId: "m08-part-2", minutes: 8, source: sources("M8-S4", ["SPEC-QT-ELIGIBILITY", "ARCH-M8", "INV-R-QT", "INV-R-CLINREV"]), copy: sceneCopy({ eyebrow: "M8 · 5 of 10", title: "Rate correction is a model", objective: "Calculate Bazett and Fridericia, inspect rate behavior, and state the caveat.", openingTutorMessage: "Keep units visible. Calculate both formulas before deciding what the difference means.", setup: ["Raw QT changes with cycle length. QTc estimates what QT might be at a standardized rate, but the estimate depends on the correction model. With QT and RR expressed in seconds, Bazett uses QT ÷ √RR and Fridericia uses QT ÷ ∛RR."], mechanismNarration: ["Their behavior diverges at rate extremes. Always report the measured QT, heart rate or RR, correction method, and uncertainty; do not treat a corrected value as rate-free truth.", "Bazett: QTcB = QT / √RR · Fridericia: QTcF = QT / ∛RR · Enter QT and RR in seconds."], clinicalConnectionHeading: "Formula-dependent estimate", clinicalConnectionBody: "Disagreement at an extreme rate is a warning to report method and context, not to choose the preferred answer.", transitionIntoTask: "Calculate both formulas, plot rate behavior, and state the caveat.", completionBody: "QTc is reported with QT, rate/RR, method, and rate-context limitation." }), layout: responsiveLayout("Rate slider with raw QT and two correction curves; mobile uses three rate cards and an accessible data table."), tutor: tutorContract({ socratic: "If RR becomes shorter, how does each denominator change, and what happens to the corrected estimate?", hints: ["Convert milliseconds to seconds before applying the formula, then convert the result back if needed.", "A disagreement at an extreme rate is a model warning, not permission to choose the preferred answer."], returnPrompt: "Back to [case]: finish QT, RR, and both formula fields before comparing them." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "qtc_prolongation", minimumTier: "A", requiredEvidence: ["Manual QT", "RR/rate", "Formula/source", "Source confidence", "QRS width"], requiredLeads: ["II", "V5", "V6"], allowedUses: ["measurement", "mechanism"], fallback: "authored_simulation", forbiddenClaims: ["Risk threshold without approved policy", "Treatment from QTc alone"] }), interactions: s4Interactions, minimumScore: 0.9, connections: { recallFrom: "M3 RR and M8-S3 QT", changesNow: "Two correction models expose rate dependence", reuseNext: "Wide-QRS confound and medication review", clinicalUse: "Prevents context-free QTc interpretation" }, handoffs: [handoff("train", "Train · QTc arithmetic and formula caveats", "qtc_prolongation", "measure", "faded")] }),
    buildScene({ id: "m08-s5", partId: "m08-part-2", minutes: 7, source: sources("M8-S5", ["SPEC-QT-ELIGIBILITY", "ARCH-M8", "INV-R-QT", "INV-R-CLINREV"]), copy: sceneCopy({ eyebrow: "M8 · 6 of 10", title: "QT includes QRS, so width matters", objective: "Recognize when a simple QTc overstates recovery time.", openingTutorMessage: "Split the interval before interpreting the total.", setup: ["QT contains both ventricular depolarization and repolarization. When QRS widens from bundle delay or pacing, QT can lengthen even if recovery has not increased by the same amount."], mechanismNarration: ["Inspect QRS duration, report the confound, and use only a reviewed method—such as a specified JT/JTc approach—when the curriculum policy provides one. Do not silently apply a narrow-QRS threshold to a wide-QRS tracing.", "QRS: depolarization · JT: J point to T end · QT: QRS onset to T end · Reviewed wide-QRS method required."], clinicalConnectionHeading: "Component before threshold", clinicalConnectionBody: "A reviewed method is required before an adjusted risk conclusion.", transitionIntoTask: "Measure QRS and QT, derive JT, and state the confound.", completionBody: "Depolarization and recovery contributions are separated before QT interpretation." }), layout: responsiveLayout("A component bar splits QT into QRS and JT beneath the waveform; mobile uses stacked labeled bars."), tutor: tutorContract({ socratic: "If QT grows by the same amount as QRS while JT stays fixed, what actually changed?", hints: ["JT begins at the J point and ends with the T wave.", "Do not invent a correction. Name the confound and use only the configured reviewed method."], returnPrompt: "Back to [case]: finish QRS, QT, and derived JT before choosing the interpretation." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "wide_qrs_qt_confound", minimumTier: "A", requiredEvidence: ["QRS/QT/QTc/rate", "Wide-QRS or pacing context", "Source confidence", "Reviewed JT/JTc method when scored"], requiredLeads: ["II", "V1", "V6"], allowedUses: ["measurement", "mechanism", "transfer"], fallback: "authored_simulation", forbiddenClaims: ["Narrow-QRS threshold silently applied", "Invented wide-QRS correction", "Medication order"] }), interactions: s5Interactions, minimumScore: 0.9, connections: { recallFrom: "M5 QRS width and M8-S3 QT", changesNow: "QT is decomposed into depolarization and recovery", reuseNext: "Medication-QT workflow and M10", clinicalUse: "Prevents paced/BBB QT overinterpretation" }, handoffs: [handoff("train", "Train · Wide-QRS QT", "wide_qrs_qt_confound", "discriminate", "faded")] }),
    buildScene({ id: "m08-s6", partId: "m08-part-3", minutes: 9, source: sources("M8-S6", ["SPEC-QT-ELIGIBILITY", "ARCH-M8", "INV-R-AUTHCTX", "INV-R-CLINREV", "CLIN-GRADING"]), copy: sceneCopy({ eyebrow: "M8 · 7 of 10", title: "Medication safety is an evidence chain", objective: "Build a reproducible QT review without embedding a stale drug list or issuing an order.", openingTutorMessage: "Measure before reading the machine or medication card.", setup: ["A medication-QT review begins with a trustworthy ECG measurement, then asks what was taken, when, at what dose, with which interacting medicines, renal/hepatic context, electrolytes, symptoms, prior ECG, and follow-up plan."], mechanismNarration: ["Drug-risk categories change and may be licensed. The platform must query a current approved source rather than teach a copied static list. In this guided scene, verify, reconcile, compare, and escalate through reviewed categories—do not create a patient-specific medication order.", "1 Verify ECG · 2 Manual QT/QTc · 3 QRS confound · 4 Reconcile medicines · 5 Check interactions/clearance · 6 Check electrolytes/symptoms · 7 Compare prior · 8 Reviewed follow-up category."], clinicalConnectionHeading: "Current source, reviewed action", clinicalConnectionBody: "Without an approved policy, the case ends after measurement and data-request ordering.", transitionIntoTask: "Measure first, then complete the staged evidence chain.", completionBody: "The medication-QT workflow is complete without a fabricated drug list or order." }), layout: responsiveLayout("Full 12-lead and eight-step timeline; context cards stay masked until manual measurement. Mobile uses a staged accordion with pinned ECG summary."), tutor: tutorContract({ socratic: "Which missing datum could change whether the corrected interval is trustworthy or actionable?", hints: ["Rate, formula, and QRS width belong beside the QTc value.", "Medication name alone is incomplete; timing, dose, interactions, clearance, electrolytes, and prior matter."], returnPrompt: "Back to step [n]: complete the ECG evidence before revealing the next context card." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "medication_qt_review", minimumTier: "A", requiredEvidence: ["Eligible QT ECG", "Manual QT/QTc and QRS", "Authored medication/context provenance", "Current licensed lookup or inert class", "Approved policy for action"], requiredLeads: ["II", "V5", "V6"], allowedUses: ["measurement", "transfer"], fallback: "lock_scene", forbiddenClaims: ["Static copyrighted drug list", "Patient-specific stop/start/dose order", "Action score without clinical review"] }), interactions: s6Interactions, minimumScore: 0.85, connections: { recallFrom: "M8-S3–S5 QT evidence", changesNow: "Measurement becomes a staged medication-safety evidence chain", reuseNext: "M10 medication case", clinicalUse: "Safe reconciliation and missing-data escalation" }, handoffs: [handoff("train", "Train · QT measurement", "qt_interval", "measure", "independent"), handoff("clinical", "Clinical · QTc safety context", "medication_qt_review", "apply_in_context", "faded", { focus: "qtc_prolongation", subskill: "apply_in_context", lane: "clinic", length: 5 })] }),
    buildScene({ id: "m08-s7", partId: "m08-part-3", minutes: 8, source: sources("M8-S7", ["SPEC-ONTOLOGY", "ARCH-M8", "INV-R-SYNTH", "INV-R-CLINREV", "INV-R-CHRONIC"]), copy: sceneCopy({ eyebrow: "M8 · 8 of 10", title: "Ion changes are patterns, not lab results", objective: "Connect broad K/Ca/Mg effects to waveform components and request confirming data.", openingTutorMessage: "Use the model to connect mechanism to components, then let the mimic show why a real ECG is not specific.", setup: ["Electrolytes influence membrane currents and therefore P waves, PR, QRS, ST, T, and QT. Potassium disturbance can alter T-wave shape and, when substantial, atrial and ventricular conduction; calcium changes can shift ST duration and QT; magnesium matters to repolarization risk but may not produce a specific surface pattern."], mechanismNarration: ["These findings overlap with drugs, ischemia, conduction disease, and normal variation. The ECG can raise a hypothesis and urgency concern; the laboratory value establishes the electrolyte measurement.", "Extracellular K — teaching continuum · Extracellular Ca — teaching continuum · Mg context — no unique waveform slider · Pattern overlap · Request laboratory confirmation."], clinicalConnectionHeading: "Hypothesis plus next datum", clinicalConnectionBody: "No model state is shown as a patient laboratory value, and no torsades/treatment mastery is awarded.", transitionIntoTask: "Change one ion, mark every component that moves, then identify the confirming datum.", completionBody: "Electrolyte-compatible waveform hypotheses are separated from laboratory confirmation." }), layout: responsiveLayout("Ion controls beside a waveform-component map; mimic layer appears after prediction. Mobile presents K and Ca as numbered experiments and Mg as context."), tutor: tutorContract({ socratic: "Which observed change is shared by more than one cause, and what datum resolves that overlap?", hints: ["Track P, PR, QRS, ST/T, and QT separately rather than searching for one signature shape.", "The ECG suggests; a measured electrolyte and clinical context confirm."], returnPrompt: "Back to the [ion] experiment: change only that control, then mark each waveform component that moved." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "electrolyte_drug_pattern", minimumTier: "A", requiredEvidence: ["Deterministic isolated-ion model", "Compatible real statement/features when used", "Overlap mimic", "Confirming lab/medication/prior datum"], allowedUses: ["mechanism", "worked_example", "transfer"], fallback: "authored_simulation", forbiddenClaims: ["Numeric electrolyte value from ECG", "Treatment order", "Torsades mastery from resting ECG"] }), interactions: s7Interactions, minimumScore: 0.84, connections: { recallFrom: "M8 ST/T/QT component descriptions", changesNow: "Ion hypotheses are tested against overlapping mimics", reuseNext: "M8 comparisons and M10 medication case", clinicalUse: "Prompts labs and context rather than waveform-only diagnosis" }, handoffs: [handoff("train", "Train · Electrolyte-pattern contrasts", "electrolyte_drug_pattern", "discriminate", "guided")],
    }),
    buildScene({ id: "m08-s8", partId: "m08-part-4", minutes: 9, source: sources("M8-S8", ["SPEC-ISCHEMIA-ELIGIBILITY", "ARCH-M8", "INV-R-ISCH", "INV-R-CHRONIC"]), copy: sceneCopy({ eyebrow: "M8 · 9 of 10", title: "Compare distributions, not slogans", objective: "Distinguish variant, pericarditis-compatible, secondary, and nonspecific patterns while preserving uncertainty.", openingTutorMessage: "Compare one discriminator at a time across all three tracings.", setup: ["Early-repolarization and age-related variants, pericarditis-compatible patterns, LVH/strain, bundle delay or pacing, lead error, and nonspecific change can overlap with ischemic-appearing ST–T findings."], mechanismNarration: ["Use lead distribution, QRS context, J-point/ST morphology, PR/baseline findings when reliable, reciprocal relationships, prior ECG, symptoms, and serial data. No single mnemonic or ratio safely settles every case.", "Distribution · QRS context · J/ST morphology · T morphology · PR/baseline evidence · Reciprocal/opposing evidence · Prior/serial · Clinical context · What remains uncertain."], clinicalConnectionHeading: "Independent discriminators", clinicalConnectionBody: "M9 owns ischemia localization and acute claims; this scene stops at pattern compatibility.", transitionIntoTask: "Complete five discriminator rows and mark one trace-level difference.", completionBody: "Variant, pericarditis-compatible, secondary, and nonspecific patterns are compared without an acute diagnosis." }), layout: responsiveLayout("Three full ECGs at identical calibration; selecting a matrix row magnifies matched leads. Mobile stacks matched panels with a pinned row label."), tutor: tutorContract({ socratic: "Which feature is independent of the same ST shape and therefore adds real discriminating evidence?", hints: ["Start with distribution and QRS context before relying on a named morphology.", "Absence of a feature is useful only when the lead and baseline can actually show it."], returnPrompt: "Back to matrix row [row]: complete that discriminator across all three ECGs." }), caseContract: caseSpec({ selectorLessonId: "ischemia-st-t", requestedConcept: "nonischemic_st_t_comparison", minimumTier: "A", requiredEvidence: ["Compatible statements and lead-level evidence", "Matched calibration/lead order", "At least five independent discriminators", "Authored context provenance"], requiredLeads: ["I", "II", "III", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"], allowedUses: ["scored_recognition", "transfer"], fallback: "lock_scene", forbiddenClaims: ["Acute ischemia diagnosis", "Culprit vessel", "Treatment action"] }), interactions: s8Interactions, minimumScore: 0.86, connections: { recallFrom: "M7 strain and M8 primary/secondary description", changesNow: "Close nonischemic patterns are compared across independent evidence rows", reuseNext: "M9 ischemia mimic laboratory", clinicalUse: "Prevents one-shape shortcut diagnosis" }, handoffs: [handoff("train", "Train · Variants and mimics", "nonischemic_st_t_comparison", "discriminate", "faded")],
    }),
    buildScene({ id: "m08-s9", partId: "m08-part-4", minutes: 10, source: sources("M8-S9", ["SPEC-QT-ELIGIBILITY", "SPEC-ISCHEMIA-ELIGIBILITY", "SPEC-MASTERY", "ARCH-MODE-HANDOFF"]), copy: sceneCopy({ eyebrow: "M8 · 10 of 10", title: "Recovery evidence under mixed conditions", objective: "Complete unannounced ST–T and QT tasks without causal overreach.", openingTutorMessage: "I’ll remain collapsed for the independent set. If you ask for help, the case pauses and the assistance level is saved.", setup: ["Use the same recovery sequence every time: calibration and quality → QRS context → baseline and J point → ST direction, magnitude, morphology, and distribution → T direction and shape → QT lead and boundaries → rate correction and formula → wide-QRS caveat → drug/electrolyte/context evidence → strongest defensible conclusion."], mechanismNarration: ["Five cases include primary/secondary contrast, descriptive ST/T, clear QT/QTc, wide-QRS QT confound, and medication/electrolyte context with intentional missing data."], clinicalConnectionHeading: "Independent recovery evidence", clinicalConnectionBody: "No acute ischemia or treatment order is keyed in this module exit.", transitionIntoTask: "Mark the decisive evidence and submit the method, limitation, conclusion, and confidence.", completionHeading: "Module complete", completionBody: "You can now anchor ST–T findings to the baseline and QRS context, measure and correct QT reproducibly, recognize wide-QRS limitations, and connect medications or electrolytes without inventing a cause or action." }), layout: responsiveLayout("Full tracing with a ten-step recovery rail; Luna collapsed; context appears only after waveform commitment. Mobile pins the current evidence step."), tutor: tutorContract({ socratic: "Which recovery field is still unsupported by a mark or measurement?", hints: ["Activation context comes before ST–T classification.", "A QTc value needs QT, rate/RR, formula, QRS context, and uncertainty."], tangentBridge: "Your exact lead, zoom, calipers, draft, and state are frozen.", returnPrompt: "Back to case [n], with your exact lead, zoom, calipers, and draft preserved." }), caseContract: caseSpec({ selectorLessonId: "qt-qtc", requestedConcept: "repolarization_qt_mixed", minimumTier: "A", requiredEvidence: ["Primary/secondary contrast", "ST/T morphology", "QT/QTc source", "Wide-QRS confound", "Intentional missing-data context"], requiredLeads: ["II", "V1", "V2", "V5", "V6", "I", "aVL"], allowedUses: ["measurement", "scored_recognition", "transfer"], fallback: "lock_scene", forbiddenClaims: ["Acute ischemia", "Electrolyte value", "Drug order", "Torsades from resting ECG"] }), interactions: s9Interactions, minimumScore: 0.82, connections: { recallFrom: "All M8 boundaries, morphology, formulas, and context", changesNow: "Targets are unannounced and recovery evidence is independently synthesized", reuseNext: "M9 ischemia and M10 clinical transfer", clinicalUse: "A reproducible recovery/QT statement with honest limits" }, handoffs: [handoff("train", "Train · QT and ST–T calibration", "repolarization_qt_mixed", "discriminate", "independent"), handoff("rapid", "Rapid · QTc recognition", "repolarization_qt_mixed", "synthesize", "independent", { focus: "qtc_prolongation", receiptConcept: "qtc_prolongation", subskill: "recognize", pace: "untimed", suggestedLength: 5 }), handoff("clinical", "Clinical · QTc safety context", "medication_qt_review", "apply_in_context", "faded", { focus: "qtc_prolongation", subskill: "apply_in_context", lane: "clinic", length: 5 })],
    }),
  ],
};

export default M08_REPOLARIZATION_MODULE;
