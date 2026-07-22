import { expect, test } from "@playwright/test";
import { collectConsoleErrors, completeAuthoredModel, registerVerifiedE2ELearner } from "./helpers";

const VECTOR_PROMPT = "Point the activation vector down and left toward lead II, then predict the dominant sign in lead II and aVR.";

async function expectNoPageOverflow(page: import("@playwright/test").Page) {
  const metrics = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    const candidates = [...document.querySelectorAll<HTMLElement>("body *")]
      .map((element) => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.left < -1 || rect.right > viewportWidth + 1)
      .filter(({ element }) => !element.closest(".viewer-stage"))
      .slice(0, 12)
      .map(({ element, rect }) => ({
        element: `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${element.className && typeof element.className === "string" ? `.${element.className.trim().replaceAll(/\s+/g, ".")}` : ""}`,
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      }));
    return {
      clientWidth: viewportWidth,
      scrollWidth: document.documentElement.scrollWidth,
      candidates,
    };
  });
  expect(metrics.scrollWidth - metrics.clientWidth, JSON.stringify(metrics, null, 2)).toBeLessThanOrEqual(1);
}

async function expectSingleVerticalScroll(page: import("@playwright/test").Page) {
  const contract = await page.evaluate(() => {
    const waveform = document.querySelector<HTMLElement>(".learning-waveform-pane")!;
    const response = document.querySelector<HTMLElement>(".learning-response-rail")!;
    const stage = document.querySelector<HTMLElement>(".viewer-stage")!;
    return {
      documentScrolls: document.documentElement.scrollHeight > document.documentElement.clientHeight + 1,
      waveformScrolls: waveform.scrollHeight > waveform.clientHeight + 1,
      responseScrolls: response.scrollHeight > response.clientHeight + 1,
      stageScrollsVertically: stage.scrollHeight > stage.clientHeight + 1,
      responseOverflowY: getComputedStyle(response).overflowY,
    };
  });
  expect(contract).toEqual({
    documentScrolls: true,
    waveformScrolls: false,
    responseScrolls: false,
    stageScrollsVertically: false,
    responseOverflowY: "visible",
  });
}

test.describe("guided ECG-first workspace", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "guided_workspace" });
  });

  test("keeps the authored model first, the tracing dominant in practice, and both drawers keyboard-safe", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/learn/leads-vectors?scene=M02.S1");

    await expect(page.getByRole("heading", { name: "Why does one beat look different twelve times?" })).toBeVisible({ timeout: 30_000 });
    const workspace = page.locator('[data-learning-workspace="true"]');
    const body = workspace.locator(".learning-workspace-body");
    const ecgPane = page.locator('[data-guided-region="ecg"]');
    const responseRail = page.getByRole("complementary", { name: "Authored model beside the ECG" });
    const sceneContext = page.locator("#production-scene-title").locator("xpath=ancestor::section[1]");
    await expect(ecgPane.locator(".viewer-stage")).toBeVisible({ timeout: 30_000 });

    await expect(workspace).toHaveAttribute("data-phase", "teaching");
    await expect(page.locator("#production-active-interaction")).toHaveCount(0);
    await expect(page.getByText("The module owns", { exact: true })).toBeVisible();
    await expect(page.getByText("Luna adds", { exact: true })).toBeVisible();

    const geometry = await Promise.all([body.boundingBox(), ecgPane.boundingBox(), responseRail.boundingBox(), sceneContext.boundingBox()]);
    expect(geometry.every(Boolean)).toBeTruthy();
    expect(geometry[3]!.y).toBeLessThan(geometry[1]!.y);
    expect(geometry[1]!.width).toBeGreaterThan(geometry[2]!.width);
    expect(geometry[2]!.width).toBeGreaterThanOrEqual(360);
    expect(await responseRail.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await expectNoPageOverflow(page);
    await expectSingleVerticalScroll(page);

    await completeAuthoredModel(page);
    await expect(workspace).toHaveAttribute("data-phase", "task");
    await expect(page.getByRole("heading", { name: VECTOR_PROMPT })).toBeVisible();

    const tutorTrigger = page.getByRole("button", { name: "Ask Luna", exact: true });
    await tutorTrigger.click();
    const tutorDialog = page.getByRole("dialog", { name: /tutor/i });
    await expect(tutorDialog).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toBeVisible();
    await expect(tutorDialog.getByRole("button", { name: "Return" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(tutorTrigger).toBeFocused();

    const sceneMapTrigger = page.getByRole("button", { name: "Contents" });
    await sceneMapTrigger.click();
    const sceneMap = page.getByRole("dialog", { name: /Leads, vectors, axis/i });
    await expect(sceneMap).toBeVisible();
    await expect(sceneMap.getByRole("button", { name: /Why does one beat look different/i })).toHaveAttribute("aria-current", "step");
    await expect(sceneMap.getByRole("button", { name: "Close" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(sceneMapTrigger).toBeFocused();
    expect(errors).toEqual([]);
  });

  test("stacks cleanly on a phone while preserving keyboard alternatives and complete ECG tool access", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await expect(page.getByRole("heading", { name: "Why does one beat look different twelve times?" })).toBeVisible({ timeout: 30_000 });

    const ecgPane = page.locator('[data-guided-region="ecg"]');
    const responseRail = page.getByRole("complementary", { name: "Authored model beside the ECG" });
    const sceneContext = page.locator("#production-scene-title").locator("xpath=ancestor::section[1]");
    await expect(ecgPane.locator(".viewer-stage")).toBeVisible({ timeout: 30_000 });
    const [ecgBox, responseBox, contextBox] = await Promise.all([ecgPane.boundingBox(), responseRail.boundingBox(), sceneContext.boundingBox()]);
    expect(ecgBox).not.toBeNull();
    expect(responseBox).not.toBeNull();
    expect(contextBox).not.toBeNull();
    expect(contextBox!.y).toBeLessThan(ecgBox!.y);
    expect(ecgBox!.y).toBeLessThan(responseBox!.y);
    await expectNoPageOverflow(page);
    await expectSingleVerticalScroll(page);

    const motionControl = page.getByRole("button", { name: "Pause motion" });
    const predictionDisclosure = page.locator("summary").filter({ hasText: "Pause and predict" });
    for (const [name, control] of [
      ["motion control", motionControl],
      ["prediction disclosure", predictionDisclosure],
    ] as const) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height, `${name} should have a 44px mobile target`).toBeGreaterThanOrEqual(44);
    }

    await completeAuthoredModel(page);
    await expect(page.getByRole("heading", { name: VECTOR_PROMPT })).toBeVisible();

    const stage = page.locator(".viewer-stage");
    await expect(stage).toBeVisible();
    expect(await stage.evaluate((node) => node.getBoundingClientRect().right <= document.documentElement.clientWidth + 1)).toBeTruthy();
    for (const label of ["Zoom in", "Zoom out", "Pan ECG left", "Pan ECG right", "Reset ECG view"]) {
      const control = page.getByRole("button", { name: label });
      await expect(control).toBeVisible();
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height, `${label} should have a 44px mobile target`).toBeGreaterThanOrEqual(44);
    }

    const slider = page.getByRole("slider", { name: "Net vector angle" });
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    await expect(slider).toBeFocused();

    const sceneMapTrigger = page.getByRole("button", { name: "Contents" });
    const tutorTrigger = page.getByRole("button", { name: "Ask Luna", exact: true });
    const curriculumLink = page.getByRole("link", { name: "Back to modules" });
    const reviewLater = page.getByRole("button", { name: "Save for later" });
    for (const [name, control] of [
      ["scene map", sceneMapTrigger],
      ["tutor", tutorTrigger],
      ["curriculum", curriculumLink],
      ["review later", reviewLater],
    ] as const) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height, `${name} should have a 44px mobile target`).toBeGreaterThanOrEqual(44);
    }

    await sceneMapTrigger.click();
    const sceneMap = page.getByRole("dialog", { name: /Leads, vectors, axis/i });
    await expect(sceneMap).toBeVisible();
    const mapBox = await sceneMap.boundingBox();
    expect(mapBox).not.toBeNull();
    expect(mapBox!.width).toBeLessThanOrEqual(390);
    await page.keyboard.press("Escape");
    await expect(sceneMapTrigger).toBeFocused();
    expect(errors).toEqual([]);
  });

  test("keeps the ECG-first and single-scroll contract at compact and midsize breakpoints", async ({ page }) => {
    for (const viewport of [
      { width: 320, height: 720 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/learn/leads-vectors?scene=M02.S1");
      await expect(page.getByRole("heading", { name: "Why does one beat look different twelve times?" })).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('[data-guided-region="ecg"] .viewer-stage')).toBeVisible({ timeout: 30_000 });
      await expectNoPageOverflow(page);
      await expectSingleVerticalScroll(page);

      const ecgBox = await page.locator('[data-guided-region="ecg"]').boundingBox();
      const responseBox = await page.getByRole("complementary", { name: "Authored model beside the ECG" }).boundingBox();
      expect(ecgBox).not.toBeNull();
      expect(responseBox).not.toBeNull();
      if (viewport.width <= 840) {
        expect(ecgBox!.y).toBeLessThan(responseBox!.y);
      } else {
        expect(ecgBox!.width).toBeGreaterThan(responseBox!.width);
      }
    }
  });
});
