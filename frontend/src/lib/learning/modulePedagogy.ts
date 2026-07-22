import type {
  LearningInteraction,
  LearningSubskill,
  ProductionModule,
  ProductionScene,
} from "@/lib/learning/interactionTypes";

export type ModuleTeachingVisual =
  | "spatial"
  | "rhythm"
  | "av"
  | "activation"
  | "tachy"
  | "voltage"
  | "recovery"
  | "territory"
  | "integration";

export type ModuleTeachingProfile = {
  visual: ModuleTeachingVisual;
  noun: string;
  stepLabels: string[];
  beatTitles: string[];
  visualSummary: string;
};

export type ModuleTeachingBeat = {
  label: string;
  title: string;
  explanation: string;
  notice: string;
  retrievalPrompt: string;
};

export type ModuleTeachingLesson = {
  intro: string;
  studioTitle: string;
  visual: ModuleTeachingVisual;
  visualSummary: string;
  beats: ModuleTeachingBeat[];
  practiceLabel: string;
};

const DEFAULT_STEP_LABELS = ["Orient", "Inspect", "Connect", "Transfer"];

export const MODULE_TEACHING_PROFILES: Record<string, ModuleTeachingProfile> = {
  "leads-vectors": {
    visual: "spatial",
    noun: "spatial model",
    stepLabels: ["Viewpoint", "Projection", "Map", "Transfer"],
    beatTitles: ["Choose a directed viewpoint", "Project the vector toward or away", "Group views that share anatomy", "Carry the spatial rule to the tracing"],
    visualSummary: "A moving cardiac vector is projected toward and away from directed ECG leads.",
  },
  "rhythm-ectopy": {
    visual: "rhythm",
    noun: "timing model",
    stepLabels: ["Timeline", "Atrial clue", "Relationship", "Name"],
    beatTitles: ["Build the ventricular timeline", "Find atrial activity on its own", "Test every atrial-to-QRS relationship", "Name only the pattern the evidence supports"],
    visualSummary: "A rhythm timeline separates ventricular timing, atrial activity, and P-to-QRS relationships.",
  },
  "av-brady": {
    visual: "av",
    noun: "conduction ladder",
    stepLabels: ["Atrial event", "Conduction", "Ventricle", "Pattern"],
    beatTitles: ["Count atrial events first", "Trace conduction through the AV node", "Account for every ventricular response", "Classify the repeated relationship"],
    visualSummary: "A ladder diagram follows atrial impulses through AV conduction to ventricular responses.",
  },
  "ventricular-conduction": {
    visual: "activation",
    noun: "activation pathway",
    stepLabels: ["Duration", "Pathway", "Polarity", "Recovery"],
    beatTitles: ["Measure width before naming shape", "Follow the ventricular activation path", "Compare the terminal lead pattern", "Separate activation from recovery"],
    visualSummary: "An authored pathway model separates QRS duration from activation morphology and recovery.",
  },
  tachyarrhythmias: {
    visual: "tachy",
    noun: "tachycardia decision map",
    stepLabels: ["Stability", "Width", "Regularity", "Mechanism"],
    beatTitles: ["Assess perfusion before elegance", "Measure QRS width explicitly", "Test regularity across the strip", "Bound the mechanism with atrial evidence"],
    visualSummary: "A bounded decision map orders stability, QRS width, regularity, and atrial evidence.",
  },
  "chambers-voltage": {
    visual: "voltage",
    noun: "voltage-evidence model",
    stepLabels: ["Signal", "Voltage", "Supporting clue", "Limit"],
    beatTitles: ["Verify that the signal is interpretable", "Measure voltage without overcalling it", "Seek independent supporting features", "State what the ECG cannot establish"],
    visualSummary: "Lead voltage and supporting features are layered without turning one threshold into a diagnosis.",
  },
  "repolarization-safety": {
    visual: "recovery",
    noun: "recovery model",
    stepLabels: ["Baseline", "Landmark", "Measure", "Context"],
    beatTitles: ["Anchor the true baseline", "Place the J point deliberately", "Measure the recovery interval", "Interpret it in rate and QRS context"],
    visualSummary: "Baseline, J point, ST–T shape, and QT boundaries are revealed in a fixed evidence order.",
  },
  "ischemia-infarction": {
    visual: "territory",
    noun: "territory-evidence map",
    stepLabels: ["Finding", "Contiguity", "Reciprocity", "Time boundary"],
    beatTitles: ["Describe the primary waveform finding", "Require an anatomic lead group", "Look for coherent opposing evidence", "Keep timing outside the static tracing"],
    visualSummary: "Contiguous lead groups, reciprocal evidence, mimics, and temporal limits remain separate layers.",
  },
  "integration-transfer": {
    visual: "integration",
    noun: "integration stack",
    stepLabels: ["Preflight", "Describe", "Prioritize", "Communicate"],
    beatTitles: ["Confirm the tracing can answer the question", "Describe before diagnosing", "Prioritize the evidence that changes action", "Communicate findings with explicit limits"],
    visualSummary: "The complete ECG read moves from signal to evidence-linked synthesis and bounded communication.",
  },
};

const PRACTICE_ONLY_TITLE = /\b(retrieval|independent|capstone|mixed\s+(?:discrimination|clerkship|transfer)|adaptive\s+handoff)\b/i;

function splitTeachingSentences(items: string[]) {
  return items.flatMap((item) => item
    .split(/(?<=[.!?])\s+(?=[A-Z0-9])/)
    .map((sentence) => sentence.trim())
    .filter(Boolean));
}

function interactionEvidenceCue(interaction: LearningInteraction | undefined) {
  if (!interaction) return "Keep the observation attached to the lead, waveform, interval, or source that supports it.";
  const cue = interaction.feedback.find((branch) => branch.evidenceCue)?.evidenceCue;
  return cue || interaction.instructions;
}

export function moduleSceneHasTeaching(moduleId: string, scene: ProductionScene) {
  if (moduleId === "foundations") return false;
  if (!MODULE_TEACHING_PROFILES[moduleId]) return false;
  if (PRACTICE_ONLY_TITLE.test(`${scene.copy.eyebrow} ${scene.copy.title}`)) return false;
  return scene.copy.mechanismNarration.length > 0;
}

export type TutorTemplateContext = {
  actionNumber: number;
  leads?: string[];
};

/**
 * Storyboard copy uses bracket tokens to describe state that the runtime must
 * supply. Never expose those authoring tokens to a learner or invite Luna to
 * invent missing case facts. Resolve what the active interaction knows and use
 * explicit, non-fabricated labels for the rest.
 */
export function resolveTutorTemplate(template: string, context: TutorTemplateContext) {
  const leadLabel = context.leads?.length ? context.leads.join("/") : "current lead";
  const replacements: Record<string, string> = {
    n: String(context.actionNumber),
    stage: String(context.actionNumber),
    "A/B": "current context",
    lead: leadLabel,
    case: "current case",
    variable: "active variable",
    criterion: "active criterion",
    beat: "current beat",
    "missing boundary": "remaining boundary",
    ion: "selected ion",
    row: "active row",
    claim: "active claim",
    "missing check": "remaining check",
  };
  return template.replace(/\[([^\]]+)\]/g, (_token, key: string) => replacements[key] ?? "current step");
}

export function buildModuleTeachingLesson(module: ProductionModule, scene: ProductionScene): ModuleTeachingLesson {
  const profile = MODULE_TEACHING_PROFILES[module.id];
  if (!profile) throw new Error(`Missing teaching profile for ${module.id}`);

  const mechanism = splitTeachingSentences(scene.copy.mechanismNarration);
  const supporting = [
    scene.copy.clinicalConnectionBody,
    scene.connections.changesNow,
    scene.connections.reuseNext,
  ].filter(Boolean);
  const sourceBeats = [...mechanism, ...supporting.filter((item) => !mechanism.includes(item))].slice(0, 4);
  const beats = (sourceBeats.length >= 2 ? sourceBeats : [scene.copy.objective, ...sourceBeats, scene.copy.clinicalConnectionBody])
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index)
    .slice(0, 4)
    .map((explanation, index) => {
      const interaction = scene.interactions[index] ?? scene.interactions.at(-1);
      return {
        label: profile.stepLabels[index] ?? DEFAULT_STEP_LABELS[index] ?? `Idea ${index + 1}`,
        title: profile.beatTitles[index] ?? `Connect idea ${index + 1} to the evidence`,
        explanation,
        notice: interactionEvidenceCue(interaction),
        retrievalPrompt: interaction?.prompt ?? scene.copy.transitionIntoTask,
      };
    });

  return {
    intro: `${scene.copy.setup[0] ?? scene.copy.objective} Build the ${profile.noun} before the scored ECG task.`,
    studioTitle: `Build the ${profile.noun}`,
    visual: profile.visual,
    visualSummary: profile.visualSummary,
    beats,
    practiceLabel: scene.copy.transitionIntoTask,
  };
}

type BloomLevel = NonNullable<ProductionScene["learningContract"]>["bloom"][number];

function inferBloom(interactions: LearningInteraction[]): BloomLevel[] {
  const kinds = new Set(interactions.map((interaction) => interaction.kind));
  const subskills = new Set(interactions.flatMap((interaction) => interaction.subskills));
  const levels = new Set<BloomLevel>();

  if (kinds.has("model_explore") || subskills.has("explain_mechanism")) levels.add("understand");
  if (["recognize", "localize", "measure"].some((skill) => subskills.has(skill as LearningSubskill))) levels.add("apply");
  if (["discriminate", "apply_in_context"].some((skill) => subskills.has(skill as LearningSubskill))) levels.add("analyze");
  if (subskills.has("calibrate_confidence")) levels.add("evaluate");
  if (subskills.has("synthesize") || kinds.has("free_response") || kinds.has("sequence")) levels.add("synthesize");
  if (!levels.size) levels.add("understand");
  return [...levels];
}

/**
 * Older native modules already contain strong source, case, feedback, and
 * assessment contracts, but predate the explicit learning contract used by
 * Foundations. Add that missing instructional/tutor boundary without changing
 * authored questions, answer keys, case eligibility, or saved scene ids.
 */
export function enrichProductionModulePedagogy(module: ProductionModule): ProductionModule {
  return {
    ...module,
    scenes: module.scenes.map((scene, index) => {
      if (scene.learningContract) return scene;
      const objectiveId = scene.caseContract?.requestedConcept
        ?? scene.handoffs[0]?.concept
        ?? `${module.id}:${scene.id}`;
      return {
        ...scene,
        learningContract: {
          objectiveId,
          bloom: inferBloom(scene.interactions),
          prerequisiteSceneIds: index > 0 ? [module.scenes[index - 1]!.id] : [],
          evidenceCeiling: !moduleSceneHasTeaching(module.id, scene)
            && scene.caseContract
            && scene.completionRule.requireIndependentAttempt
            ? "independent_immediate_candidate"
            : "guided",
          criticalRules: scene.caseContract?.forbiddenClaims ?? [],
        },
      };
    }),
  };
}
