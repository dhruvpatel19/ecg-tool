import { notFound, redirect } from "next/navigation";
import { ProductionModuleExperience } from "@/components/learning/ProductionModuleExperience";
import {
  PRODUCTION_CURRICULUM,
  PRODUCTION_CURRICULUM_BY_ID,
  PRODUCTION_CURRICULUM_COUNT,
} from "@/lib/learning/modules";

export function generateStaticParams() {
  return PRODUCTION_CURRICULUM
    // Foundations has a static owner-bound migration wrapper at the same URL.
    // Excluding it here prevents duplicate static generation for that route.
    .filter((entry) => entry.kind === "native" && entry.id !== "foundations")
    .map((entry) => ({ moduleId: entry.id }));
}

export default async function GuidedModulePage({ params }: { params: Promise<{ moduleId: string }> }) {
  const { moduleId } = await params;
  const entry = PRODUCTION_CURRICULUM_BY_ID.get(moduleId);
  if (!entry) notFound();
  if (entry.kind === "external_host") redirect(entry.route);

  const index = PRODUCTION_CURRICULUM.findIndex((candidate) => candidate.id === entry.id);
  const prior = index > 0 ? PRODUCTION_CURRICULUM[index - 1] : undefined;
  const next = index >= 0 && index < PRODUCTION_CURRICULUM.length - 1 ? PRODUCTION_CURRICULUM[index + 1] : undefined;

  return (
    <ProductionModuleExperience
      module={entry.module}
      totalModules={PRODUCTION_CURRICULUM_COUNT}
      priorModule={prior ? { id: prior.id, shortTitle: prior.shortTitle } : undefined}
      nextModule={next ? { id: next.id, shortTitle: next.shortTitle } : undefined}
    />
  );
}
