import { expect, test, type Page } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";

let owner = "";

async function openStandaloneScene(page: Page, current: number) {
  // Seed state from a same-origin page that is not running the Foundations
  // boot sequence; otherwise its pending CASES_READY callback can overwrite the
  // requested scene with S0 between localStorage.setItem and reload.
  await page.goto("/");
  await page.evaluate(
    ({ key, scene }) => {
      localStorage.setItem(key, JSON.stringify({ completed: {}, current: scene, nv: {}, skipped: {}, testedOut: {} }));
    },
    { key: `foundations_state_v1:${owner}`, scene: current },
  );
  await page.goto(`/foundations/index.html?owner=${owner}`);
  await page.getByRole("button", { name: "Resume" }).press("Enter");
}

test.describe("Foundations accessibility and tutor continuity", () => {
  test.beforeEach(async ({ page }) => {
    const account = await registerVerifiedE2ELearner(page, {
      prefix: "foundations_accessibility",
      displayName: "Foundation Learner",
    });
    owner = account.user.userId;
    await page.route(`**/api/backend/learners/${owner}/pathway-progress**`, (route) => {
      const body = route.request().method() === "PUT"
        ? route.request().postDataJSON() as { items?: unknown[] }
        : null;
      return route.fulfill({ json: { learnerId: owner, items: body?.items ?? [] } });
    });
    await page.goto("/");
    await page.evaluate((key) => localStorage.removeItem(key), `foundations_state_v1:${owner}`);
  });

  test("keyboard-only waveform completion records a guided schematic receipt and preserves tangent state", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const guidedBodies: Array<Record<string, unknown>> = [];
    await page.route("**/api/backend/learning-events/guided", async (route) => {
      guidedBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ eventId: 1, requestedEvidenceLevel: "guided", effectiveEvidenceLevel: "guided", receipts: [] }),
      });
    });

    await page.goto("/learn/foundations");
    const lesson = page.frameLocator('iframe[title="Foundations of the ECG Read"]');

    await expect(lesson.getByRole("heading", { name: "A gentle start" })).toBeVisible();
    await expect(lesson.getByText(/Real PTB-XL ECG \d+ · lead II/)).toBeVisible();
    await lesson.getByRole("button", { name: "Next ›" }).press("Enter");
    await expect(lesson.getByText("Interactive mechanism schematic — not a patient ECG.", { exact: false })).toBeVisible();

    const beatPosition = lesson.getByRole("slider", { name: "One-beat animation position" });
    await beatPosition.focus();
    await beatPosition.press("End");
    await lesson.getByRole("button", { name: "Show P / QRS / T ▸" }).press("Enter");

    await lesson.getByRole("button", { name: "P", exact: true }).press("Enter");
    await lesson.getByRole("button", { name: "Place on the small first bump" }).press("Enter");
    await lesson.getByRole("button", { name: "QRS", exact: true }).press("Enter");
    await lesson.getByRole("button", { name: "Place on the tall sharp spike" }).press("Enter");
    await lesson.getByRole("button", { name: "T", exact: true }).press("Enter");
    await lesson.getByRole("button", { name: "Place on the rounded last bump" }).press("Enter");

    await expect(lesson.getByText("That’s the whole vocabulary of a heartbeat", { exact: false })).toBeVisible();
    await expect(lesson.getByRole("button", { name: "Next ›" })).toBeEnabled();
    await expect.poll(() => guidedBodies.length).toBe(1);
    expect(guidedBodies[0]).toMatchObject({
      moduleId: "foundations",
      sceneId: "S1",
      interactionId: "s1-wave-label-placement",
      concept: "waveform_components",
      subskills: ["localize"],
      correct: true,
      evidenceLevel: "guided",
      caseProvenance: "authored_simulation",
      caseEligible: false,
    });

    const tutorInput = lesson.getByPlaceholder("Ask about any concept…", { exact: false });
    await tutorInput.focus();
    await tutorInput.fill("What causes a wide QRS?");
    await tutorInput.press("Enter");
    const returnButton = lesson.getByRole("button", { name: "↩ Return to One beat, one wave" });
    await expect(returnButton).toBeVisible();
    await returnButton.focus();
    await returnButton.press("Enter");
    await expect(lesson.getByText("Your scene and unfinished interaction are unchanged", { exact: false })).toBeVisible();
    await expect(lesson.getByRole("button", { name: "Next ›" })).toBeEnabled();
    await expect(lesson.locator("#sceneRoot")).toBeFocused();
    expect(errors).toEqual([]);
  });

  test("missing PTB teaching bundle fails closed without mounting a simulated tracing", async ({ page }) => {
    await page.route("**/foundations/data/cases.json", async (route) => {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "unavailable" }) });
    });

    await page.goto("/learn/foundations");
    const lesson = page.frameLocator('iframe[title="Foundations of the ECG Read"]');

    await expect(lesson.getByRole("heading", { name: "Foundations is temporarily unavailable" })).toBeVisible();
    await expect(lesson.getByText("No simulated ECG will replace missing real data.", { exact: false })).toBeVisible();
    await expect(lesson.locator(".real-case-label, .model-disclosure, .ecg-svg")).toHaveCount(0);
    await expect(lesson.getByRole("button", { name: "Next ›" })).toBeDisabled();
    await expect(lesson.getByRole("button", { name: "‹ Back" })).toBeDisabled();
  });

  test("remote tutor output is rendered as text and cannot inject lesson DOM", async ({ page }) => {
    await page.route("**/api/backend/tutor/foundations", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tutorMessage:
            '<img src=x onerror="window.__remoteInjected=1"><form id="remote-form"><input></form><style>body{display:none}</style>Line one\nLine two',
        }),
      });
    });

    await page.goto("/learn/foundations");
    const lesson = page.frameLocator('iframe[title="Foundations of the ECG Read"]');
    const input = lesson.getByPlaceholder("Ask about any concept…", { exact: false });
    await input.fill("What is an interval?");
    await input.press("Enter");

    const body = lesson.locator(".msg.ai .body").last();
    await expect(body).toContainText("<img src=x");
    await expect(body).toContainText("Line one");
    await expect(body).toContainText("Line two");
    await expect(body.locator("img, form, style, iframe, a")).toHaveCount(0);
    await expect(lesson.locator("body")).toBeVisible();
    expect(
      await lesson.locator("body").evaluate(
        () => (window as typeof window & { __remoteInjected?: number }).__remoteInjected,
      ),
    ).toBeUndefined();
  });

  test("every former drag-only engine exposes a visible keyboard or tap path", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await openStandaloneScene(page, 2);
    await expect(page.getByRole("slider", { name: "Start marker position" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Start right" })).toBeVisible();

    await openStandaloneScene(page, 3);
    const stripOneReadable = page.getByRole("button", { name: "Strip 1: readable" });
    await expect(stripOneReadable).toBeVisible();
    await expect(page.getByRole("button", { name: "Strip 2: too noisy" })).toBeVisible();
    await stripOneReadable.focus();
    await expect.poll(() => stripOneReadable.evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe("none");

    await openStandaloneScene(page, 6);
    await expect(page.getByRole("slider", { name: "PR start handle" })).toBeVisible();
    await expect(page.getByRole("button", { name: "End right" })).toBeVisible();

    await openStandaloneScene(page, 7);
    await page.getByRole("button", { name: "A · flat TP stretch between beats" }).press("Enter");
    await expect(page.getByRole("slider", { name: "ST level in millivolts" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Set at baseline" })).toBeVisible();

    await openStandaloneScene(page, 8);
    await expect(page.getByRole("slider", { name: "Precordial lead from V1 through V6" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next lead" })).toBeVisible();

    await openStandaloneScene(page, 9);
    await expect(page.getByRole("slider", { name: "QRS axis in degrees" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Go to left axis" })).toBeVisible();
    await expect(page.getByRole("slider", { name: "QRS axis vector" })).toBeVisible();

    expect(errors).toEqual([]);
  });
});
