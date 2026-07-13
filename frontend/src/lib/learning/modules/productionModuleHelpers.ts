import type {
  AccessibilityContract,
  CaseContract,
  CrossModeHandoff,
  FeedbackBranch,
  LearningSubskill,
  ProductionScene,
  SceneLayoutContract,
  SourceReference,
  TutorSceneContract,
  VerbatimSceneCopy,
} from "@/lib/learning/interactionTypes";

export const SPEC_DOCUMENT = "ECG_PLATFORM_SPEC.md";
export const STORYBOARD_DOCUMENT = "docs/storyboards/VERBATIM_M01_M03.md";

export function source(
  section: string,
  requirementIds: string[],
  document = SPEC_DOCUMENT,
): SourceReference {
  return { document, section, requirementIds };
}

export function storyboardSource(sceneId: string): SourceReference {
  return source(sceneId, [`VERBATIM-${sceneId}`], STORYBOARD_DOCUMENT);
}

export function access(
  instructions: string,
  keyboardAlternative: string,
  screenReaderSummary: string,
  reducedMotionAlternative = "No motion is required. The same states and values are available as numbered text frames.",
): AccessibilityContract {
  return { instructions, keyboardAlternative, screenReaderSummary, reducedMotionAlternative };
}

export function feedback(
  correctBody: string,
  partialBody: string,
  incorrectBody: string,
  evidenceCue: string,
  extras: FeedbackBranch[] = [],
): FeedbackBranch[] {
  return [
    { id: "correct", when: "correct", heading: "Evidence aligned", body: correctBody },
    { id: "partial", when: "partially_correct", heading: "Partly supported", body: partialBody, evidenceCue },
    { id: "incorrect", when: "incorrect", heading: "Not yet", body: incorrectBody, evidenceCue },
    ...extras,
  ];
}

export function sceneCopy(values: VerbatimSceneCopy): VerbatimSceneCopy {
  return values;
}

export function layout(values: SceneLayoutContract): SceneLayoutContract {
  return values;
}

export function tutor(
  socraticPrompts: string[],
  hintLadder: string[],
  tangentBridge: string,
  returnPrompt: string,
): TutorSceneContract {
  return {
    socraticPrompts,
    hintLadder,
    tangentBridge,
    returnPrompt,
    caseUnavailablePrompt: "This learning case did not pass its content check. Your progress is safe; choose another case or try again later.",
  };
}

export function caseContract(values: CaseContract): CaseContract {
  return values;
}

export function handoff(
  mode: CrossModeHandoff["mode"],
  label: string,
  concept: string,
  subskill: LearningSubskill,
  supportLevel: CrossModeHandoff["supportLevel"],
): CrossModeHandoff {
  return { mode, label, concept, subskill, supportLevel };
}

export function productionScene(values: ProductionScene): ProductionScene {
  return values;
}

