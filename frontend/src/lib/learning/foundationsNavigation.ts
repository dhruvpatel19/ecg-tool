export const FOUNDATIONS_SCENE_NAVIGATION = [
  { id: "S0", title: "Your ECG reading roadmap" },
  { id: "S1", title: "One beat, one electrical story" },
  { id: "S2", title: "The grid is your ruler" },
  { id: "S3", title: "Readable for what?" },
  { id: "S4", title: "Regular first, then rate" },
  { id: "S5", title: "Is there a sinus P-wave pattern?" },
  { id: "S6", title: "Measure PR and QRS" },
  { id: "S7", title: "Baseline, J point, ST, T, and QT" },
  { id: "S8", title: "One event, twelve directed views" },
  { id: "S9", title: "Axis is the coarse QRS direction" },
  { id: "S10", title: "Put the full read together" },
  { id: "S11", title: "Complete a read with less guidance" },
  { id: "S12", title: "Two complete ECG reads" },
] as const;

export type FoundationsSceneId = typeof FOUNDATIONS_SCENE_NAVIGATION[number]["id"];

const sceneById = new Map<string, typeof FOUNDATIONS_SCENE_NAVIGATION[number]>(
  FOUNDATIONS_SCENE_NAVIGATION.map((scene) => [scene.id, scene]),
);

export function foundationsSceneNavigation(sceneId: string | null | undefined) {
  return sceneId ? sceneById.get(sceneId) ?? null : null;
}

export function foundationsSceneHref(sceneId: string | null | undefined) {
  const scene = foundationsSceneNavigation(sceneId);
  return scene ? `/learn/foundations?scene=${encodeURIComponent(scene.id)}` : null;
}
