import type { AccessibilityContract, FeedbackBranch, LearningInteraction } from "@/lib/learning/interactionTypes";

const access = (instructions: string, keyboardAlternative: string, screenReaderSummary: string, reducedMotionAlternative?: string): AccessibilityContract => ({
  instructions,
  keyboardAlternative,
  screenReaderSummary,
  reducedMotionAlternative,
});

const branches = (
  correctBody: string,
  incorrectBody: string,
  evidenceCue: string,
  partialBody = "You have part of the evidence. Recheck the missing or extra element before resubmitting.",
): FeedbackBranch[] => [
  { id: "correct", when: "correct", heading: "Evidence aligned", body: correctBody },
  { id: "partial", when: "partially_correct", heading: "Part of the geometry is right", body: partialBody, evidenceCue },
  { id: "incorrect", when: "incorrect", heading: "Rebuild it from the viewing direction", body: incorrectBody, evidenceCue },
];

export const GUIDED_INTERACTIONS_BY_SCENE: Record<string, LearningInteraction[]> = {
  "leads-vectors:2.0": [
    {
      id: "2.0-sweep-sequence",
      kind: "sequence",
      prompt: "Put the first four orientation checks in the order you would use before interpreting a finding.",
      instructions: "Use the up and down controls. Build the order from acquisition truth toward interpretation.",
      subskills: ["synthesize"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 1,
      cards: [
        { id: "calibration", label: "Confirm calibration and paper speed", detail: "Know what each box means." },
        { id: "quality", label: "Decide what is readable", detail: "Name any domain that is not assessable." },
        { id: "layout", label: "Orient to the lead layout", detail: "One evolving event, twelve directed views." },
        { id: "finding", label: "Describe the waveform finding", detail: "Only after the view is trustworthy." },
      ],
      correctOrder: ["calibration", "quality", "layout", "finding"],
      feedback: branches(
        "Yes. Calibration and quality establish what the image can support; lead orientation tells you where you are looking; only then is a waveform claim defensible.",
        "A finding cannot outrun acquisition truth. Put calibration and readability before lead orientation, and orientation before the waveform claim.",
        "Ask: Can I trust the ruler? Can I trust the signal? Which view is this? What do I see?",
      ),
      accessibility: access(
        "Reorder four cards into a complete orientation sequence.",
        "Tab to a card's Move earlier or Move later button and press Enter or Space.",
        "Four ordered cards: calibration, readability, lead layout, then waveform finding.",
      ),
    },
  ],
  "leads-vectors:2.1": [
    {
      id: "2.1-lead-i-vector",
      kind: "vector_lab",
      prompt: "Rotate the net depolarization vector so it points directly toward lead I's positive pole.",
      instructions: "Lead I's positive direction is toward the patient's left arm. Set the arrow, then commit.",
      subskills: ["explain_mechanism"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 2,
      initialAngleDeg: 110,
      targetAngleDeg: 0,
      toleranceDeg: 10,
      targetLabel: "large positive projection in lead I (0°)",
      predictions: [{ lead: "I", expected: "positive" }],
      feedback: branches(
        "The vector is aligned with lead I's positive axis, so its projection is strongly positive. You changed direction, not conduction time.",
        "Follow the lead arrow toward its positive pole. A vector directed away becomes negative; a perpendicular vector becomes nearly isoelectric.",
        "Set the dial close to 0°—the positive axis of lead I.",
      ),
      accessibility: access(
        "Rotate a vector to the positive axis of lead I.",
        "Focus the angle slider. Use Left/Right Arrow for 1° steps or Page Up/Page Down for larger steps.",
        "A circular frontal-plane dial with lead I positive at zero degrees.",
        "The dial is static; the selected angle and predicted polarity are announced as text.",
      ),
    },
  ],
  "leads-vectors:2.2": [
    {
      id: "2.2-perpendicular-vector",
      kind: "vector_lab",
      prompt: "Make the QRS nearly isoelectric in lead I by rotating the vector perpendicular to lead I.",
      instructions: "Choose either perpendicular direction. This exercise uses +90° as the target so the projection onto lead I approaches zero.",
      subskills: ["explain_mechanism"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 2,
      initialAngleDeg: 15,
      targetAngleDeg: 90,
      toleranceDeg: 10,
      targetLabel: "near-zero projection in lead I (+90°)",
      predictions: [{ lead: "I", expected: "isoelectric" }, { lead: "aVF", expected: "positive" }],
      feedback: branches(
        "At roughly +90°, the vector is perpendicular to lead I and directed toward aVF. Lead I approaches isoelectric while aVF becomes positive.",
        "Do not change the length of the QRS to solve a projection problem. Rotate the direction until it forms a right angle with lead I.",
        "Lead I is 0°. A perpendicular direction is +90° or −90°; use +90° here.",
      ),
      accessibility: access(
        "Rotate the vector until it is perpendicular to lead I.",
        "Focus the angle slider and use arrow keys to set +90°.",
        "A frontal-plane vector lab asking for a vector perpendicular to lead I and toward aVF.",
        "The selected angle and both lead predictions are available without animation.",
      ),
    },
  ],
  "leads-vectors:2.3": [
    {
      id: "2.3-frontal-leads",
      kind: "lead_select",
      prompt: "Select every lead that belongs to the frontal plane.",
      instructions: "Choose the limb and augmented limb leads. Leave the horizontal-plane precordial leads unselected.",
      subskills: ["localize"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 1,
      selectionMode: "multiple",
      correctLeads: ["I", "II", "III", "aVR", "aVL", "aVF"],
      rejectExtraSelections: true,
      feedback: branches(
        "Correct. I, II, III, aVR, aVL, and aVF form the frontal-plane view set. V1–V6 view the horizontal plane.",
        "The frontal plane is built from the four limb electrodes: the three bipolar limb leads plus aVR, aVL, and aVF.",
        "Select I, II, III, aVR, aVL, and aVF—six views in total.",
      ),
      accessibility: access(
        "Select all six frontal-plane leads from a 12-lead grid.",
        "Tab through the lead buttons and press Space to toggle each selection.",
        "Twelve lead buttons. Correct frontal-plane set: I, II, III, aVR, aVL, and aVF.",
      ),
    },
  ],
  "leads-vectors:2.4": [
    {
      id: "2.4-precordial-order",
      kind: "lead_select",
      prompt: "Select V1 through V6 in anatomical viewing order from right/anterior toward left/lateral.",
      instructions: "Each selected lead receives an order number. If you make a mistake, select that lead again to remove it and continue.",
      subskills: ["localize"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 2,
      selectionMode: "ordered",
      allowedLeads: ["V1", "V2", "V3", "V4", "V5", "V6"],
      correctLeads: ["V1", "V2", "V3", "V4", "V5", "V6"],
      rejectExtraSelections: true,
      feedback: branches(
        "Yes. V1→V6 moves across the horizontal plane toward the left ventricle; the normal R/S balance usually shifts along that same sequence.",
        "Follow the chest leads numerically from V1 to V6. The order is a changing viewpoint, not six unrelated beats.",
        "Begin at V1 and continue numerically through V6.",
      ),
      accessibility: access(
        "Choose six precordial leads in anatomical order.",
        "Tab through V1–V6 and press Space in the desired order. The current order number is announced visually and in button text.",
        "Six selectable precordial leads arranged as V1 through V6.",
      ),
    },
  ],
  "leads-vectors:2.5": [
    {
      id: "2.5-inferior-contiguous",
      kind: "lead_select",
      prompt: "Select the contiguous inferior lead group—and no unrelated views.",
      instructions: "Choose the leads that look at adjacent inferior myocardium. This is a localization task, not an infarction diagnosis.",
      subskills: ["localize", "discriminate"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 2,
      selectionMode: "multiple",
      correctLeads: ["II", "III", "aVF"],
      rejectExtraSelections: true,
      feedback: branches(
        "II, III, and aVF are the contiguous inferior views. A coherent finding there is localized as inferior before its cause is named.",
        "Contiguous means anatomically neighboring viewpoints. Do not mix an anterior or lateral lead into the inferior group.",
        "Use the three downward-facing frontal views: II, III, and aVF.",
      ),
      accessibility: access(
        "Select the three contiguous inferior leads.",
        "Tab through the lead buttons and press Space to select or deselect.",
        "Twelve lead buttons. Correct inferior group: II, III, and aVF.",
      ),
    },
  ],
  "leads-vectors:2.6": [
    {
      id: "2.6-axis-refinement",
      kind: "vector_lab",
      prompt: "Place a vector that makes lead I positive, aVF negative, and lead II still positive.",
      instructions: "This is the leftward-but-potentially-normal sector between 0° and −30°. Aim near its center.",
      subskills: ["localize", "explain_mechanism"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 2,
      initialAngleDeg: 65,
      targetAngleDeg: -15,
      toleranceDeg: 14,
      targetLabel: "leftward normal-axis extension (about −15°)",
      predictions: [{ lead: "I", expected: "positive" }, { lead: "aVF", expected: "negative" }, { lead: "II", expected: "positive" }],
      feedback: branches(
        "That vector is leftward, so I is positive and aVF negative, but it remains within about −30° because lead II is still positive. State the boundary rather than overcalling left-axis deviation.",
        "I-positive/aVF-negative does not finish the problem. Use lead II to decide whether the vector remains above roughly −30°.",
        "Place the vector between 0° and −30°, near −15°.",
      ),
      accessibility: access(
        "Set a frontal-plane vector in the leftward normal-axis extension.",
        "Focus the slider and use arrow keys to choose an angle between 0° and −30°.",
        "A vector dial targeting approximately minus fifteen degrees, with predicted polarity in leads I, aVF, and II.",
        "No motion is required; all polarity consequences are stated in text after submission.",
      ),
    },
  ],
  "leads-vectors:2.7": [
    {
      id: "2.7-progression-explanation",
      kind: "free_response",
      prompt: "Write the strongest defensible next step when poor R-wave progression appears in isolation.",
      instructions: "Use finding → uncertainty → verification. Do not assign infarction from progression alone.",
      subskills: ["discriminate", "explain_mechanism", "calibrate_confidence"],
      requiredForCompletion: true,
      maxAttemptsBeforeScaffold: 1,
      responseLabel: "Your one-sentence evidence statement",
      placeholder: "I see …; because … is uncertain, I would verify … before …",
      sentenceFrame: "Describe the finding, name at least two plausible non-infarction explanations/checks, and state what would increase confidence.",
      minimumCharacters: 45,
      rubric: [
        { id: "finding", label: "Names poor R-wave progression", acceptedConcepts: ["poor r wave progression", "poor r-wave progression", "reduced r wave progression"], required: true, misconceptionIfMissing: "finding_not_described" },
        { id: "placement", label: "Checks lead placement", acceptedConcepts: ["lead placement", "electrode placement", "repeat ecg", "repeat the ecg"], required: true, misconceptionIfMissing: "placement_not_checked" },
        { id: "prior", label: "Seeks prior/comparison", acceptedConcepts: ["prior ecg", "previous ecg", "compare with prior", "comparison ecg"], required: true, misconceptionIfMissing: "prior_not_sought" },
        { id: "uncertainty", label: "Avoids automatic infarction", acceptedConcepts: ["does not prove infarction", "not diagnostic of infarction", "before calling infarction", "cannot diagnose infarction", "uncertain cause"], required: true, misconceptionIfMissing: "progression_overcalled_as_mi" },
        { id: "variant", label: "Mentions normal variation or rotation/body habitus", acceptedConcepts: ["normal variation", "normal variant", "rotation", "body habitus"], required: false },
      ],
      feedback: branches(
        "Your statement separates the observed progression pattern from its cause, verifies acquisition, and seeks comparison before escalating the label.",
        "The answer needs all four links: name poor R-wave progression; verify placement; compare a prior; and state that progression alone does not diagnose infarction.",
        "Use this frame: ‘Poor R-wave progression is present; I would verify lead placement and compare a prior ECG before attributing it to infarction.’",
        "Your sentence contains some of the reasoning chain. Add the missing acquisition check, comparison, or uncertainty statement.",
      ),
      accessibility: access(
        "Write a one-sentence differential and verification plan.",
        "Type in the text area. Speech-to-text and paste are supported by the browser.",
        "A text response requiring poor R-wave progression, lead-placement verification, prior comparison, and uncertainty about infarction.",
      ),
    },
  ],
};

export function interactionsForScene(moduleId: string, sceneId: string) {
  return GUIDED_INTERACTIONS_BY_SCENE[`${moduleId}:${sceneId}`] ?? [];
}
