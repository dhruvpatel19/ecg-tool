import { expect, test } from "@playwright/test";
import { gradeInteraction } from "../src/lib/learning/gradeInteraction";
import { NATIVE_PRODUCTION_MODULES } from "../src/lib/learning/modules";

const allInteractions = NATIVE_PRODUCTION_MODULES.flatMap((module) => (
  module.scenes.flatMap((scene) => scene.interactions)
));

test("mechanism labs cover every authored ECG model family with complete frames", () => {
  const labs = allInteractions.filter((interaction) => interaction.kind === "model_explore");
  expect(new Set(labs.map((interaction) => interaction.model))).toEqual(new Set([
    "cardiac_cycle",
    "vector_projection",
    "av_ladder",
    "bundle_activation",
    "reentry",
    "repolarization",
  ]));

  for (const lab of labs) {
    expect(new Set(lab.frames.map((frame) => frame.id)).size).toBe(lab.frames.length);
    expect(lab.requiredFrameIds.length).toBeGreaterThan(0);
    expect(lab.frames.every((frame) => frame.label.trim() && frame.narration.trim())).toBe(true);
    expect(lab.requiredFrameIds.every((id) => lab.frames.some((frame) => frame.id === id))).toBe(true);

    const complete = gradeInteraction(lab, lab.requiredFrameIds, 1);
    expect(complete.correct, lab.id).toBe(true);
    if (lab.requiredFrameIds.length > 1) {
      const incomplete = gradeInteraction(lab, lab.requiredFrameIds.slice(0, -1), 1);
      expect(incomplete.correct, lab.id).toBe(false);
      expect(incomplete.partial, lab.id).toBe(true);
    }
  }
});

test("three-pattern discriminator boards grade every column rather than a prose proxy", () => {
  const triadIds = ["m08-s8-triad", "m09-s8-triad"];
  for (const id of triadIds) {
    const board = allInteractions.find((interaction) => interaction.id === id);
    if (!board || board.kind !== "compare") throw new Error(`Missing ${id}`);

    expect(board.thirdCaseConcept).toBeTruthy();
    expect(board.dimensions.length).toBeGreaterThanOrEqual(5);
    expect(board.dimensions.every((dimension) => dimension.thirdAnswer?.trim())).toBe(true);

    const complete = Object.fromEntries(board.dimensions.map((dimension) => [dimension.id, {
      left: dimension.leftAnswer,
      right: dimension.rightAnswer,
      third: dimension.thirdAnswer,
    }]));
    expect(gradeInteraction(board, complete, 1).correct, id).toBe(true);

    const first = board.dimensions[0];
    const swapped = {
      ...complete,
      [first.id]: {
        left: first.thirdAnswer,
        right: first.rightAnswer,
        third: first.leftAnswer,
      },
    };
    expect(gradeInteraction(board, swapped, 1).correct, id).toBe(false);
  }
});

test("all comparison boards have deterministic authored evidence rows", () => {
  const boards = allInteractions.filter((interaction) => interaction.kind === "compare");
  expect(boards.length).toBeGreaterThanOrEqual(10);
  for (const board of boards) {
    expect(board.dimensions.length, board.id).toBeGreaterThan(0);
    expect(new Set(board.dimensions.map((dimension) => dimension.id)).size, board.id).toBe(board.dimensions.length);
    expect(board.dimensions.every((dimension) => (
      dimension.label.trim() && dimension.leftAnswer.trim() && dimension.rightAnswer.trim()
    )), board.id).toBe(true);
  }
});
