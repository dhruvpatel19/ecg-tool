import type { LearningInteraction, ProductionModule, SourceReference } from "@/lib/learning/interactionTypes";
import { AUTHORITATIVE_REQUIREMENTS } from "@/lib/learning/sourceRequirements";

export type CurriculumValidationIssue = {
  path: string;
  message: string;
};

/**
 * Some curriculum experiences intentionally live outside the native scene
 * renderer. This descriptor makes their coverage auditable without fabricating
 * ProductionScene data that the hosted artifact does not execute.
 */
export type ExternalModuleCoverageDescriptor = {
  kind: "external_host";
  id: string;
  order: number;
  title: string;
  shortTitle: string;
  route: string;
  duration: string;
  outcome: string;
  prerequisiteIds: string[];
  sourceRequirementIds: string[];
  sources: SourceReference[];
  coveredSubtopicsByRequirement: Record<string, string[]>;
  implementation: {
    artifact: string;
    sceneCount: number;
    progressContract: string;
  };
};

export type NativeRequirementCoverageDescriptor = {
  requirementId: string;
  moduleId: string;
  scenes: Array<{
    sceneId: string;
    coveredSubtopics: string[];
  }>;
};

export type ProductionCurriculumValidationOptions = {
  externalModules?: ExternalModuleCoverageDescriptor[];
  nativeRequirementCoverage?: NativeRequirementCoverageDescriptor[];
  expectedModuleCount?: number;
  requireContiguousOrder?: boolean;
};

const OPAQUE_CASE_POOL_SLOT = /^[a-z][a-z0-9_-]*(?::[A-Za-z][A-Za-z0-9_-]*)+$/;

function validateInteraction(interaction: LearningInteraction, path: string): CurriculumValidationIssue[] {
  const issues: CurriculumValidationIssue[] = [];
  if (!interaction.prompt.trim()) issues.push({ path, message: "Interaction prompt is required." });
  if (!interaction.instructions.trim()) issues.push({ path, message: "Interaction instructions are required." });
  if (!interaction.subskills.length) issues.push({ path, message: "At least one assessed subskill is required." });
  if (!interaction.feedback.some((branch) => branch.when === "correct")) {
    issues.push({ path, message: "A correct feedback branch is required." });
  }
  if (!interaction.feedback.some((branch) => branch.when === "incorrect" || branch.when === "not_assessable")) {
    issues.push({ path, message: "An incorrect or not-assessable feedback branch is required." });
  }
  if (!interaction.accessibility.keyboardAlternative.trim()) {
    issues.push({ path, message: "A keyboard alternative is required." });
  }
  if (!interaction.accessibility.screenReaderSummary.trim()) {
    issues.push({ path, message: "A screen-reader summary is required." });
  }

  if (interaction.kind === "single_select") {
    if (!interaction.options.some((option) => option.id === interaction.correctOptionId)) {
      issues.push({ path, message: "correctOptionId must reference an option." });
    }
  }
  if (interaction.kind === "multi_select") {
    const ids = new Set(interaction.options.map((option) => option.id));
    if (!interaction.correctOptionIds.length || interaction.correctOptionIds.some((id) => !ids.has(id))) {
      issues.push({ path, message: "Every correctOptionId must reference an option." });
    }
  }
  if (interaction.kind === "sequence") {
    const cardIds = interaction.cards.map((card) => card.id);
    if (new Set(cardIds).size !== cardIds.length || interaction.correctOrder.length !== cardIds.length) {
      issues.push({ path, message: "Sequence cards and correctOrder must be unique and the same length." });
    }
  }
  if (interaction.kind === "lead_select" && !interaction.correctLeads.length) {
    issues.push({ path, message: "Lead selection needs at least one correct lead." });
  }
  if (interaction.kind === "vector_lab" && (interaction.toleranceDeg <= 0 || interaction.toleranceDeg > 45)) {
    issues.push({ path, message: "Vector tolerance must be greater than 0° and no more than 45°." });
  }
  if (interaction.kind === "caliper" && interaction.target.toleranceMs <= 0) {
    issues.push({ path, message: "Caliper tolerance must be positive." });
  }
  if (interaction.kind === "march" && interaction.minimumMarkers < 3) {
    issues.push({ path, message: "Marching requires at least three markers." });
  }
  if (interaction.kind === "compare") {
    const ids = interaction.dimensions.map((dimension) => dimension.id);
    if (!ids.length || new Set(ids).size !== ids.length) {
      issues.push({ path, message: "Comparison dimensions must be present and uniquely identified." });
    }
    if (interaction.dimensions.some((dimension) => !dimension.label.trim() || !dimension.leftAnswer.trim() || !dimension.rightAnswer.trim())) {
      issues.push({ path, message: "Every comparison row needs a label and authored answers for both primary columns." });
    }
    if (interaction.thirdCaseConcept && interaction.dimensions.some((dimension) => !dimension.thirdAnswer?.trim())) {
      issues.push({ path, message: "A three-column comparison needs an authored third answer in every row." });
    }
    if (!interaction.thirdCaseConcept && interaction.dimensions.some((dimension) => dimension.thirdAnswer)) {
      issues.push({ path, message: "A third comparison answer requires a third case concept." });
    }
  }
  if (interaction.kind === "free_response" && !interaction.rubric.some((criterion) => criterion.required)) {
    issues.push({ path, message: "A free response needs at least one required rubric criterion." });
  }
  if (interaction.kind === "free_response" && interaction.forbiddenClaims?.some((claim) => (
    !claim.id.trim() || !claim.label.trim() || !claim.misconception.trim() || !claim.terms.length || claim.terms.some((term) => !term.trim())
  ))) {
    issues.push({ path, message: "Every forbidden free-response claim needs an id, label, misconception, and non-empty terms." });
  }
  if (interaction.kind === "clinical_stage" && !interaction.stages.length) {
    issues.push({ path, message: "A clinical-stage interaction needs at least one stage." });
  }
  if (interaction.kind === "hotspot_map") {
    const ids = new Set(interaction.hotspots.map((hotspot) => hotspot.id));
    if (!interaction.correctHotspotIds.length || interaction.correctHotspotIds.some((id) => !ids.has(id))) {
      issues.push({ path, message: "Every correct hotspot must exist on the map." });
    }
    if (interaction.hotspots.some((hotspot) => hotspot.xPercent < 0 || hotspot.xPercent > 100 || hotspot.yPercent < 0 || hotspot.yPercent > 100)) {
      issues.push({ path, message: "Hotspot coordinates must be percentages from 0 to 100." });
    }
  }
  if (interaction.kind === "model_explore") {
    const ids = new Set(interaction.frames.map((frame) => frame.id));
    if (ids.size !== interaction.frames.length) {
      issues.push({ path, message: "Model frame ids must be unique." });
    }
    if (interaction.frames.some((frame) => !frame.label.trim() || !frame.narration.trim())) {
      issues.push({ path, message: "Every model frame needs a visible label and mechanism narration." });
    }
    if (!interaction.requiredFrameIds.length || interaction.requiredFrameIds.some((id) => !ids.has(id))) {
      issues.push({ path, message: "Every required model frame must exist." });
    }
  }
  if (interaction.kind === "numeric_entry" && interaction.target.tolerance <= 0) {
    issues.push({ path, message: "Numeric tolerance must be positive." });
  }
  if (interaction.kind === "pairing") {
    const left = new Set(interaction.left.map((item) => item.id));
    const right = new Set(interaction.right.map((item) => item.id));
    if (Object.entries(interaction.correctPairs).some(([a, b]) => !left.has(a) || !right.has(b))) {
      issues.push({ path, message: "Every correct pair must reference defined left and right items." });
    }
  }
  if (interaction.kind === "categorize") {
    const items = new Set(interaction.items.map((item) => item.id));
    const categories = new Set(interaction.categories.map((item) => item.id));
    if (Object.entries(interaction.correctCategoryByItem).some(([item, category]) => !items.has(item) || !categories.has(category))) {
      issues.push({ path, message: "Every category mapping must reference defined items and categories." });
    }
  }
  if (interaction.kind === "waveform_lab") {
    const ids = new Set(interaction.targets.map((target) => target.id));
    if (!interaction.requiredTargetIds.length || interaction.requiredTargetIds.some((id) => !ids.has(id))) {
      issues.push({ path, message: "Every required authored-waveform target must exist." });
    }
    if (interaction.durationMs <= 0 || interaction.toleranceMs <= 0) {
      issues.push({ path, message: "Authored-waveform duration and tolerance must be positive." });
    }
    if (interaction.task === "march" && (interaction.minimumMarkers ?? 0) < 3) {
      issues.push({ path, message: "Authored-waveform marching requires at least three markers." });
    }
    if ((interaction.task === "interval" || interaction.task === "region") && interaction.requiredTargetIds.some((id) => {
      const target = interaction.targets.find((item) => item.id === id);
      return target?.startMs === undefined || target.endMs === undefined;
    })) {
      issues.push({ path, message: "Every required authored interval/region needs start and end boundaries." });
    }
    if (interaction.task === "point_targets" && interaction.requiredTargetIds.some((id) => interaction.targets.find((item) => item.id === id)?.timeMs === undefined)) {
      issues.push({ path, message: "Every required authored point target needs a time." });
    }
  }
  return issues;
}

export function validateProductionCurriculum(
  modules: ProductionModule[],
  options: ProductionCurriculumValidationOptions = {},
): CurriculumValidationIssue[] {
  const issues: CurriculumValidationIssue[] = [];
  const externalModules = options.externalModules ?? [];
  const nativeRequirementCoverage = options.nativeRequirementCoverage ?? [];
  const moduleIds = new Set<string>();
  const moduleOrders = new Map<number, string>();
  const sceneIds = new Set<string>();

  for (const [moduleIndex, module] of modules.entries()) {
    const modulePath = `modules[${moduleIndex}](${module.id})`;
    if (moduleIds.has(module.id)) issues.push({ path: modulePath, message: "Duplicate module id." });
    moduleIds.add(module.id);
    const existingAtOrder = moduleOrders.get(module.order);
    if (existingAtOrder) issues.push({ path: `${modulePath}.order`, message: `Order ${module.order} is already used by ${existingAtOrder}.` });
    else moduleOrders.set(module.order, module.id);
    if (!Number.isInteger(module.order) || module.order < 1) issues.push({ path: `${modulePath}.order`, message: "Module order must be a positive integer." });
    if (!module.sourceRequirementIds.length) issues.push({ path: modulePath, message: "Module must cite source requirements." });
    if (!module.scenes.length) issues.push({ path: modulePath, message: "Module must contain scenes." });

    for (const [sceneIndex, scene] of module.scenes.entries()) {
      const scenePath = `${modulePath}.scenes[${sceneIndex}](${scene.id})`;
      const globalSceneId = `${module.id}:${scene.id}`;
      if (sceneIds.has(globalSceneId)) issues.push({ path: scenePath, message: "Duplicate scene id in module." });
      sceneIds.add(globalSceneId);
      if (!scene.source.length) issues.push({ path: scenePath, message: "Scene must cite at least one source requirement." });
      if (!scene.interactions.length) issues.push({ path: scenePath, message: "Scene must contain a learner interaction." });
      if (!scene.layout.desktop.trim() || !scene.layout.laptop.trim() || !scene.layout.mobile.trim()) {
        issues.push({ path: `${scenePath}.layout`, message: "Desktop, laptop, and mobile layout contracts are required." });
      }
      if (!scene.layout.focusOrder.length) issues.push({ path: `${scenePath}.layout`, message: "A keyboard/screen-reader focus order is required." });
      if (!scene.tutor.socraticPrompts.length) issues.push({ path: `${scenePath}.tutor`, message: "At least one Socratic prompt is required." });
      if (!scene.tutor.hintLadder.length) issues.push({ path: `${scenePath}.tutor`, message: "A tutor hint ladder is required." });
      if (scene.learningContract) {
        if (!scene.learningContract.objectiveId.trim()) issues.push({ path: `${scenePath}.learningContract`, message: "A learning objective id is required." });
        if (!scene.learningContract.bloom.length) issues.push({ path: `${scenePath}.learningContract`, message: "At least one Bloom level is required." });
        const scenePosition = module.scenes.findIndex((item) => item.id === scene.id);
        for (const prerequisiteSceneId of scene.learningContract.prerequisiteSceneIds) {
          const prerequisitePosition = module.scenes.findIndex((item) => item.id === prerequisiteSceneId);
          if (prerequisitePosition < 0) issues.push({ path: `${scenePath}.learningContract`, message: `Unknown prerequisite scene: ${prerequisiteSceneId}.` });
          else if (prerequisitePosition >= scenePosition) issues.push({ path: `${scenePath}.learningContract`, message: `Prerequisite ${prerequisiteSceneId} must precede ${scene.id}.` });
        }
      }
      // A scene may deliberately have no cross-mode launch when the receiving
      // mode cannot assess the same construct with an exact executable
      // destination. Requiring a link here previously forced clinically false
      // or mastery-inflating handoffs. Present handoffs are validated at launch
      // by the destination contract; truthful absence is valid curriculum data.
      const interactionIds = new Set<string>();
      for (const [interactionIndex, interaction] of scene.interactions.entries()) {
        const interactionPath = `${scenePath}.interactions[${interactionIndex}](${interaction.id})`;
        if (interactionIds.has(interaction.id)) issues.push({ path: interactionPath, message: "Duplicate interaction id in scene." });
        interactionIds.add(interaction.id);
        issues.push(...validateInteraction(interaction, interactionPath));
      }
      for (const requiredId of scene.completionRule.requiredInteractionIds) {
        if (!interactionIds.has(requiredId)) {
          issues.push({ path: `${scenePath}.completionRule`, message: `Unknown required interaction: ${requiredId}.` });
        }
      }
      if (scene.completionRule.minimumScore <= 0 || scene.completionRule.minimumScore > 1) {
        issues.push({ path: `${scenePath}.completionRule`, message: "minimumScore must be within (0, 1]." });
      }
      if (scene.caseContract?.allowedUses.includes("scored_recognition") && scene.caseContract.fallback === "contrast_only") {
        issues.push({ path: `${scenePath}.caseContract`, message: "A scored-recognition case cannot fall back to contrast-only use." });
      }
      if (scene.caseContract?.casePoolSlot && !OPAQUE_CASE_POOL_SLOT.test(scene.caseContract.casePoolSlot)) {
        issues.push({ path: `${scenePath}.caseContract.casePoolSlot`, message: "Case pool slots must be opaque namespaced keys, not corpus identifiers." });
      }
      if (scene.caseContract?.retryCasePoolSlot && !OPAQUE_CASE_POOL_SLOT.test(scene.caseContract.retryCasePoolSlot)) {
        issues.push({ path: `${scenePath}.caseContract.retryCasePoolSlot`, message: "Retry case pool slots must be opaque namespaced keys, not corpus identifiers." });
      }
      if (scene.caseContract?.retryCasePoolSlot && !scene.caseContract.casePoolSlot) {
        issues.push({ path: `${scenePath}.caseContract`, message: "A retry pool slot requires a primary case pool slot." });
      }
      if (module.id === "foundations" && scene.caseContract && !scene.caseContract.casePoolSlot) {
        issues.push({ path: `${scenePath}.caseContract`, message: "Foundations case contracts require a server-governed opaque pool slot." });
      }
    }
  }

  for (const [moduleIndex, module] of externalModules.entries()) {
    const modulePath = `externalModules[${moduleIndex}](${module.id})`;
    if (moduleIds.has(module.id)) issues.push({ path: modulePath, message: "Duplicate module id across native and external modules." });
    moduleIds.add(module.id);
    const existingAtOrder = moduleOrders.get(module.order);
    if (existingAtOrder) issues.push({ path: `${modulePath}.order`, message: `Order ${module.order} is already used by ${existingAtOrder}.` });
    else moduleOrders.set(module.order, module.id);
    if (!Number.isInteger(module.order) || module.order < 1) issues.push({ path: `${modulePath}.order`, message: "Module order must be a positive integer." });
    if (!module.title.trim() || !module.shortTitle.trim()) issues.push({ path: modulePath, message: "External module title and short title are required." });
    if (!module.route.startsWith("/")) issues.push({ path: `${modulePath}.route`, message: "External module route must be an absolute application path." });
    if (!module.implementation.artifact.trim()) issues.push({ path: `${modulePath}.implementation.artifact`, message: "Hosted artifact path is required." });
    if (!module.implementation.progressContract.trim()) issues.push({ path: `${modulePath}.implementation.progressContract`, message: "Hosted progress contract is required." });
    if (!Number.isInteger(module.implementation.sceneCount) || module.implementation.sceneCount < 1) {
      issues.push({ path: `${modulePath}.implementation.sceneCount`, message: "Hosted scene count must be a positive integer." });
    }
    if (!module.sourceRequirementIds.length) issues.push({ path: modulePath, message: "External module must cite source requirements." });
    if (!module.sources.length) issues.push({ path: `${modulePath}.sources`, message: "External module must cite its authored source artifact." });
    if (module.sources.some((source) => !source.document.trim() || !source.section.trim() || !source.requirementIds.length)) {
      issues.push({ path: `${modulePath}.sources`, message: "Every external source citation needs a document, section, and requirement id." });
    }
    const cited = new Set(module.sources.flatMap((source) => source.requirementIds));
    for (const requirementId of module.sourceRequirementIds) {
      if (!cited.has(requirementId)) {
        issues.push({ path: `${modulePath}.sources`, message: `${requirementId} is declared but not tied to an external source citation.` });
      }
    }
  }

  const nativeCoverageByRequirement = new Map<string, NativeRequirementCoverageDescriptor>();
  for (const [coverageIndex, coverage] of nativeRequirementCoverage.entries()) {
    const coveragePath = `nativeRequirementCoverage[${coverageIndex}](${coverage.requirementId})`;
    if (nativeCoverageByRequirement.has(coverage.requirementId)) {
      issues.push({ path: coveragePath, message: "Duplicate native requirement coverage descriptor." });
      continue;
    }
    nativeCoverageByRequirement.set(coverage.requirementId, coverage);
    const requirement = AUTHORITATIVE_REQUIREMENTS.find((item) => item.id === coverage.requirementId);
    if (!requirement) {
      issues.push({ path: coveragePath, message: "Coverage descriptor references an unknown authoritative requirement." });
      continue;
    }
    if (requirement.primaryModuleId !== coverage.moduleId) {
      issues.push({ path: `${coveragePath}.moduleId`, message: `${coverage.requirementId} belongs to primary module ${requirement.primaryModuleId}, not ${coverage.moduleId}.` });
    }
    const module = modules.find((item) => item.id === coverage.moduleId);
    if (!module) {
      issues.push({ path: `${coveragePath}.moduleId`, message: `Native coverage module does not exist: ${coverage.moduleId}.` });
      continue;
    }
    if (!coverage.scenes.length) issues.push({ path: `${coveragePath}.scenes`, message: "Native requirement coverage must name at least one scene." });
    const moduleSceneIds = new Set(module.scenes.map((scene) => scene.id));
    const seenCoverageSceneIds = new Set<string>();
    const allowedSubtopics = new Set(requirement.requiredSubtopics);
    for (const [sceneIndex, sceneCoverage] of coverage.scenes.entries()) {
      const scenePath = `${coveragePath}.scenes[${sceneIndex}](${sceneCoverage.sceneId})`;
      if (seenCoverageSceneIds.has(sceneCoverage.sceneId)) issues.push({ path: scenePath, message: "Duplicate scene in one requirement coverage descriptor." });
      seenCoverageSceneIds.add(sceneCoverage.sceneId);
      if (!moduleSceneIds.has(sceneCoverage.sceneId)) issues.push({ path: scenePath, message: `Mapped scene does not exist in ${module.id}.` });
      if (!sceneCoverage.coveredSubtopics.length) issues.push({ path: `${scenePath}.coveredSubtopics`, message: "Mapped scene must cover at least one required subtopic." });
      for (const subtopic of sceneCoverage.coveredSubtopics) {
        if (!allowedSubtopics.has(subtopic)) {
          issues.push({ path: `${scenePath}.coveredSubtopics`, message: `Unknown subtopic for ${coverage.requirementId}: ${subtopic}.` });
        }
      }
    }
  }

  const totalModuleCount = modules.length + externalModules.length;
  if (options.expectedModuleCount !== undefined && totalModuleCount !== options.expectedModuleCount) {
    issues.push({ path: "curriculum", message: `Expected ${options.expectedModuleCount} modules, found ${totalModuleCount}.` });
  }
  if (options.requireContiguousOrder) {
    for (let expectedOrder = 1; expectedOrder <= totalModuleCount; expectedOrder += 1) {
      if (!moduleOrders.has(expectedOrder)) {
        issues.push({ path: "curriculum.order", message: `Module order is not contiguous: missing ${expectedOrder}.` });
      }
    }
  }

  for (const [moduleIndex, module] of modules.entries()) {
    for (const prerequisite of module.prerequisiteIds) {
      if (!moduleIds.has(prerequisite)) {
        issues.push({ path: `modules[${moduleIndex}](${module.id}).prerequisiteIds`, message: `Unknown prerequisite module: ${prerequisite}.` });
      }
    }
  }
  for (const [moduleIndex, module] of externalModules.entries()) {
    for (const prerequisite of module.prerequisiteIds) {
      if (!moduleIds.has(prerequisite)) {
        issues.push({ path: `externalModules[${moduleIndex}](${module.id}).prerequisiteIds`, message: `Unknown prerequisite module: ${prerequisite}.` });
      }
    }
  }

  const citedByModule = new Map<string, Set<string>>();
  for (const module of modules) {
    const cited = new Set<string>();
    module.sourceRequirementIds.forEach((id) => cited.add(id));
    module.scenes.forEach((scene) => scene.source.forEach((source) => source.requirementIds.forEach((id) => cited.add(id))));
    citedByModule.set(module.id, cited);
  }
  for (const module of externalModules) {
    const cited = new Set(module.sourceRequirementIds);
    module.sources.forEach((source) => source.requirementIds.forEach((id) => cited.add(id)));
    citedByModule.set(module.id, cited);
  }
  for (const requirement of AUTHORITATIVE_REQUIREMENTS) {
    const module = modules.find((item) => item.id === requirement.primaryModuleId)
      ?? externalModules.find((item) => item.id === requirement.primaryModuleId);
    if (!module) {
      issues.push({ path: "authoritativeCoverage", message: `${requirement.id} has no primary module ${requirement.primaryModuleId}.` });
      continue;
    }
    if (!citedByModule.get(module.id)?.has(requirement.id)) {
      issues.push({ path: `modules(${module.id}).source`, message: `${requirement.id} is not cited by its primary teaching module.` });
    }
    if ("kind" in module && module.kind === "external_host") {
      const coveredSubtopics = new Set(module.coveredSubtopicsByRequirement[requirement.id] ?? []);
      for (const requiredSubtopic of requirement.requiredSubtopics) {
        if (!coveredSubtopics.has(requiredSubtopic)) {
          issues.push({
            path: `externalModules(${module.id}).coveredSubtopicsByRequirement.${requirement.id}`,
            message: `Missing authoritative subtopic: ${requiredSubtopic}.`,
          });
        }
      }
    } else {
      const coverage = nativeCoverageByRequirement.get(requirement.id);
      if (!coverage) {
        issues.push({
          path: `nativeRequirementCoverage(${requirement.id})`,
          message: `Native primary module ${requirement.primaryModuleId} has no scene-level required-subtopic map.`,
        });
        continue;
      }
      const coveredSubtopics = new Set(coverage.scenes.flatMap((scene) => scene.coveredSubtopics));
      for (const requiredSubtopic of requirement.requiredSubtopics) {
        if (!coveredSubtopics.has(requiredSubtopic)) {
          issues.push({
            path: `nativeRequirementCoverage(${requirement.id}).coveredSubtopics`,
            message: `Missing authoritative subtopic: ${requiredSubtopic}.`,
          });
        }
      }
    }
  }
  return issues;
}
