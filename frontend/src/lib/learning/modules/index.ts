import type { ProductionModule } from "@/lib/learning/interactionTypes";
import type { ExternalModuleCoverageDescriptor } from "@/lib/learning/validateCurriculum";
import { validateProductionCurriculum } from "@/lib/learning/validateCurriculum";
import { M01_FOUNDATIONS_MODULE } from "@/lib/learning/modules/m01Foundations";
import { M02_LEADS_VECTORS_MODULE } from "@/lib/learning/modules/m02LeadsVectors";
import { M03_RHYTHM_LOGIC_MODULE } from "@/lib/learning/modules/m03RhythmLogic";
import { M04_AV_CONDUCTION_MODULE } from "@/lib/learning/modules/m04AvConduction";
import { M05_VENTRICULAR_CONDUCTION_MODULE } from "@/lib/learning/modules/m05VentricularConduction";
import { M06_TACHYARRHYTHMIAS_MODULE } from "@/lib/learning/modules/m06Tachyarrhythmias";
import { M07_CHAMBERS_VOLTAGE_MODULE } from "@/lib/learning/modules/m07ChambersVoltage";
import { M08_REPOLARIZATION_MODULE } from "@/lib/learning/modules/m08Repolarization";
import { M09_ISCHEMIA_MODULE } from "@/lib/learning/modules/m09Ischemia";
import { M10_INTEGRATION_MODULE } from "@/lib/learning/modules/m10Integration";
import { NATIVE_REQUIREMENT_COVERAGE } from "@/lib/learning/modules/nativeRequirementCoverage";
import { enrichProductionModulePedagogy } from "@/lib/learning/modulePedagogy";

export type NativeProductionCurriculumEntry = {
  kind: "native";
  id: string;
  order: number;
  title: string;
  shortTitle: string;
  route: string;
  module: ProductionModule;
};

export type ProductionCurriculumEntry = NativeProductionCurriculumEntry | ExternalModuleCoverageDescriptor;

export const NATIVE_PRODUCTION_MODULES: ProductionModule[] = [
  M01_FOUNDATIONS_MODULE,
  M02_LEADS_VECTORS_MODULE,
  M03_RHYTHM_LOGIC_MODULE,
  M04_AV_CONDUCTION_MODULE,
  M05_VENTRICULAR_CONDUCTION_MODULE,
  M06_TACHYARRHYTHMIAS_MODULE,
  M07_CHAMBERS_VOLTAGE_MODULE,
  M08_REPOLARIZATION_MODULE,
  M09_ISCHEMIA_MODULE,
  M10_INTEGRATION_MODULE,
].map(enrichProductionModulePedagogy);

export const EXTERNAL_PRODUCTION_MODULES: ExternalModuleCoverageDescriptor[] = [];

const nativeEntries: NativeProductionCurriculumEntry[] = NATIVE_PRODUCTION_MODULES.map((module) => ({
  kind: "native",
  id: module.id,
  order: module.order,
  title: module.title,
  shortTitle: module.shortTitle,
  route: `/learn/${module.id}`,
  module,
}));

export const PRODUCTION_CURRICULUM: ProductionCurriculumEntry[] = [
  ...EXTERNAL_PRODUCTION_MODULES,
  ...nativeEntries,
].sort((left, right) => left.order - right.order);

export const PRODUCTION_CURRICULUM_ISSUES = validateProductionCurriculum(NATIVE_PRODUCTION_MODULES, {
  externalModules: EXTERNAL_PRODUCTION_MODULES,
  nativeRequirementCoverage: NATIVE_REQUIREMENT_COVERAGE,
  expectedModuleCount: 10,
  requireContiguousOrder: true,
});

if (PRODUCTION_CURRICULUM_ISSUES.length) {
  const details = PRODUCTION_CURRICULUM_ISSUES
    .map((issue, index) => `${index + 1}. ${issue.path}: ${issue.message}`)
    .join("\n");
  throw new Error(`Production curriculum validation failed with ${PRODUCTION_CURRICULUM_ISSUES.length} issue(s):\n${details}`);
}

export const PRODUCTION_CURRICULUM_BY_ID = new Map(
  PRODUCTION_CURRICULUM.map((entry) => [entry.id, entry] as const),
);

export const PRODUCTION_MODULE_BY_ID = new Map(
  NATIVE_PRODUCTION_MODULES.map((module) => [module.id, module] as const),
);

export const PRODUCTION_CURRICULUM_COUNT = PRODUCTION_CURRICULUM.length;

export { M01_FOUNDATIONS_MODULE, NATIVE_REQUIREMENT_COVERAGE };
