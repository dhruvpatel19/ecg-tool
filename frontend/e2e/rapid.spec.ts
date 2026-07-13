import { test, expect, type Page } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

async function registerRapidLearner(page: Page) {
  const username = `r_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 8)}`;
  const response = await page.request.post("/api/backend/auth/register", {
    data: { username, password: "Sup3r-Secret-Pw!" },
  });
  expect(response.ok()).toBeTruthy();
}

test.describe("Mode 3 · Rapid", () => {
  test("synthesis handoff exposes only complete-read paces and the exact receipt gate", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await registerRapidLearner(page);
    await page.goto("/rapid?focus=normal_ecg&receiptConcept=integrated_interpretation&subskill=synthesize&returnTo=/review");
    await expect(page.getByText(/Independent synthesis gate/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Time-pressured quick-look/ })).toBeDisabled();
    await expect(page.getByRole("button", { name: /Untimed practice/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("link", { name: "Return to lesson" })).toHaveAttribute("href", "/review");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("configures an untimed round, commits a blinded read, and shows deterministic feedback", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await registerRapidLearner(page);
    await page.goto("/rapid");

    await expect(page.getByRole("heading", { name: "Rapid ECG rounds" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Ward read/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Time-pressured quick-look/ })).toBeVisible();
    const untimed = page.getByRole("button", { name: /Untimed practice/ });
    await untimed.click();
    await expect(untimed).toHaveAttribute("aria-pressed", "true");
    await page.reload();
    await expect(page.getByRole("button", { name: /Untimed practice/ })).toHaveAttribute("aria-pressed", "true");

    const servedRound = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    await page.getByRole("button", { name: "Start untimed practice" }).click();
    const roundResponse = await servedRound;
    expect(roundResponse.ok()).toBeTruthy();
    const served = await roundResponse.json() as { current: { packet: Record<string, unknown> & {
      ptbxl_plus: { fiducials: { rois: Array<{ lead: string; concept: string; timeStartSec: number }> } };
    } } };
    const packet = served.current.packet;
    expect(packet.blinded).toBe(true);
    expect(packet).not.toHaveProperty("supported_objectives");
    const qrs = packet.ptbxl_plus.fiducials.rois.find((roi) => roi.lead === "II" && roi.concept === "qrs_complex");
    expect(qrs).toBeTruthy();

    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible();
    await expect(page.getByText("Tutor silent until commitment", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toHaveCount(0);
    await expect(page.getByRole("list", { name: "ECG interpretation framework" })).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: "Rate" })).toHaveAttribute("aria-current", "step");

    await page.getByRole("button", { name: "Normal ECG" }).click();
    await page.getByLabel("One-line synthesis").fill("Normal ECG pattern on rapid review.");
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.getByLabel("Keyboard task lead").selectOption("II");
    await page.getByLabel("Time cursor (seconds)").fill(qrs!.timeStartSec.toFixed(3));
    await page.getByRole("button", { name: "Grade selected point" }).click();
    await expect(page.getByText("Validated QRS mark recorded for this read.")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("One-line synthesis")).toHaveValue("Normal ECG pattern on rapid review.");
    await expect(page.getByRole("button", { name: "Normal ECG" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Validated QRS mark recorded for this read.")).toBeVisible();

    const submissionRequest = page.waitForRequest((request) => /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/submit$/.test(new URL(request.url()).pathname));
    const submissionResponse = page.waitForResponse((response) => /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/submit$/.test(new URL(response.url()).pathname));
    await page.getByRole("button", { name: "Commit interpretation" }).click();
    const submitBody = (await submissionRequest).postDataJSON() as { traceEvidence?: { mode?: string; point?: { lead?: string } } };
    expect(submitBody.traceEvidence).toMatchObject({ mode: "point", point: { lead: "II" } });
    const submitted = await (await submissionResponse).json() as {
      current: { packet: Record<string, unknown>; answer: { grade: { masteryDelta: Record<string, number>; legacyObjectiveMasterySuppressed: boolean } } };
      receipts: Array<{ concept: string; subskill: string; accepted: boolean }>;
    };
    expect(submitted.current.packet).toHaveProperty("supported_objectives");
    expect(submitted.current.answer.grade.masteryDelta).toEqual({});
    expect(submitted.current.answer.grade.legacyObjectiveMasterySuppressed).toBe(true);
    expect(submitted.receipts).toContainEqual(expect.objectContaining({ concept: "qrs_complex", subskill: "localize", accepted: true }));

    await expect(page.getByRole("heading", { name: "Deterministic feedback" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("heading", { name: "Recognized" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
    const caseTutor = page.getByRole("region", { name: "Conversational ECG tutor" });
    await expect(caseTutor).toBeVisible();
    await expect(caseTutor.getByRole("button", { name: "Open tutor" })).toBeVisible();
    await expect(page.getByText(/server-verified QRS localization/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Next ECG" })).toBeVisible();
    await page.evaluate(() => window.sessionStorage.clear());
    await page.reload();
    await expect(page.getByRole("heading", { name: "Deterministic feedback" })).toBeVisible();
    await expect(page.getByText(/server-verified QRS localization/i)).toBeVisible();
    await expect(page.locator(".rapid-timer")).toHaveAttribute("data-clock-state", "complete");
    await expect(page.locator(".rapid-timer")).toHaveText("Read complete");
    await expect(page.locator(".rapid-clockbar")).toHaveCount(0);
    await expect(page.getByLabel("Committed trace proof")).toContainText(/QRS in lead II/);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("tachyarrhythmia handoff constrains the first case and preserves return navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await registerRapidLearner(page);
    await page.goto("/rapid?focus=tachyarrhythmia_mixed&subskill=recognize&returnTo=/learn/tachyarrhythmias?scene=m06-s11");
    await page.getByRole("button", { name: /Untimed practice/ }).click();

    const targeted = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    await page.getByRole("button", { name: "Start untimed practice" }).click();
    const response = await targeted;
    expect(response.ok()).toBeTruthy();
    const payload = await response.json() as { targetObjectives: string[] };
    expect(payload.targetObjectives).toContain("atrial_fibrillation");

    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: "Return to lesson" })).toHaveAttribute("href", "/learn/tachyarrhythmias?scene=m06-s11");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("emergency Focus Stack includes PVC, waits for the rendered paper, and fits 390px", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await registerRapidLearner(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route("**/api/backend/cases/*/waveform?*", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1_200));
      await route.continue();
    });
    await page.goto("/rapid?focus=premature_ventricular_complex&subskill=recognize");
    await page.getByRole("button", { name: /Time-pressured quick-look/ }).click();
    await page.getByRole("button", { name: "Start time-pressured quick-look" }).click();

    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    const timer = page.locator(".rapid-timer");
    await expect(timer).toHaveAttribute("data-clock-state", "waiting");
    await expect(timer).toHaveText("ECG loading");
    await expect(timer).toHaveAttribute("data-clock-state", "running", { timeout: 10_000 });
    const startingSeconds = Number.parseInt((await timer.textContent()) ?? "0", 10);
    expect(startingSeconds).toBeGreaterThanOrEqual(18);

    const dominant = page.getByLabel("One dominant ECG finding");
    await expect(page.locator(".rapid-recognition")).toHaveAttribute("data-catalog-loaded", "true");
    await expect(dominant.getByRole("option", { name: /Premature ventricular complex/i })).toBeAttached();
    const catalogResponse = await page.request.get("/api/backend/concepts");
    const catalog = await catalogResponse.json() as { practiceGroups: Array<{ concepts: Array<{ id: string; available: boolean }> }> };
    const selectableIds = await dominant.locator("option").evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value));
    const missingAvailableConcepts = catalog.practiceGroups
      .flatMap((group) => group.concepts)
      .filter((concept) => concept.available && !selectableIds.includes(concept.id));
    expect(missingAvailableConcepts).toEqual([]);
    await dominant.selectOption("premature_ventricular_complex");
    const commit = page.getByRole("button", { name: "Commit interpretation" });
    await expect(dominant).toBeVisible();
    await expect(commit).toBeVisible();
    await expect(commit).toBeEnabled();

    const geometry = await page.evaluate(() => {
      const select = document.querySelector<HTMLSelectElement>('select[aria-label="One dominant ECG finding"]');
      const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent?.includes("Commit interpretation"));
      const selectBox = select?.getBoundingClientRect();
      const buttonBox = button?.getBoundingClientRect();
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        selectFits: Boolean(selectBox && selectBox.left >= 0 && selectBox.right <= window.innerWidth),
        buttonFits: Boolean(buttonBox && buttonBox.left >= 0 && buttonBox.right <= window.innerWidth),
        submitWidth: buttonBox?.width ?? 0,
      };
    });
    expect(geometry.documentFits).toBe(true);
    expect(geometry.selectFits).toBe(true);
    expect(geometry.buttonFits).toBe(true);
    expect(geometry.submitWidth).toBeLessThan(390);

    await commit.click();
    await expect(page.getByRole("region", { name: "Conversational ECG tutor" })).toBeVisible({ timeout: 60_000 });
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("automatically requests a receipt-grounded AI debrief with deterministic handoffs", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await registerRapidLearner(page);
    type DeterministicReceiptSample = {
      caseId: string;
      score: number;
      timedOut: boolean;
      responseMs: number | null;
      correct: string[];
      missed: string[];
      overcalled: string[];
      misconceptions: string[];
    };
    type RapidDebriefBody = {
      message?: string;
      viewerState?: {
        activity?: string;
        pace?: string;
        completedCaseCount?: number;
        recentDeterministicReceipts?: DeterministicReceiptSample[];
        deterministicOnly?: boolean;
      };
    };
    const debriefBodies: RapidDebriefBody[] = [];
    const serverServedBeforeNext: string[][] = [];
    let latestQrs: { lead: string; timeStartSec: number } | null = null;
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (!response.ok() || !/\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)) return;
      const requestBody = response.request().postDataJSON() as { activate?: boolean };
      if (requestBody.activate) return;
      const selection = await response.json() as {
        round?: { servedCount?: number; recentServed?: string[] };
        current?: { case?: { caseId?: string }; packet?: { ptbxl_plus?: { fiducials?: { rois?: Array<{ lead: string; concept: string; timeStartSec: number }> } } } };
      };
      if (!selection.current?.case?.caseId) return;
      latestQrs = selection.current?.packet?.ptbxl_plus?.fiducials?.rois?.find((roi) => roi.lead === "II" && roi.concept === "qrs_complex") ?? null;
      expect(selection.round?.servedCount).toBe(selection.round?.recentServed?.length ?? 0);
      serverServedBeforeNext.push(selection.round?.recentServed ?? []);
    });
    await page.route("**/api/backend/tutor/message", async (route) => {
      debriefBodies.push(route.request().postDataJSON() as RapidDebriefBody);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          threadId: "rapid-round-test",
          tutorMessage: "Across this round, preserve your rhythm anchor before deciding whether conduction or repolarization explains the dominant abnormality.",
          feedback: "",
          viewerActions: [],
          objectiveUpdates: [],
          misconceptions: [],
          uncertaintyWarnings: [],
          suggestedNextStep: "Contrast the most frequent miss with one close mimic.",
          socraticQuestion: "Which earlier finding should constrain your next differential?",
          citedEvidence: ["deterministic rapid receipts"],
          onLessonTopic: true,
        }),
      });
    });
    await page.goto("/rapid");
    await page.getByRole("button", { name: /Untimed practice/ }).click();
    await page.getByRole("button", { name: "Start untimed practice" }).click();

    for (let index = 0; index < 5; index += 1) {
      await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
      await expect.poll(() => latestQrs, { timeout: 15_000 }).not.toBeNull();
      const tracePoint = latestQrs!;
      latestQrs = null;
      await page.getByText("Keyboard / precise-entry alternative").click();
      await page.getByLabel("Keyboard task lead").selectOption(tracePoint.lead);
      await page.getByLabel("Time cursor (seconds)").fill(tracePoint.timeStartSec.toFixed(3));
      await page.getByRole("button", { name: "Grade selected point" }).click();
      await expect(page.getByText("Validated QRS mark recorded for this read.")).toBeVisible();
      await page.getByRole("button", { name: "Normal ECG" }).click();
      await page.getByLabel("One-line synthesis").fill("Systematic rapid read committed for deterministic review.");
      await page.getByRole("button", { name: "Commit interpretation" }).click();
      await expect(page.getByRole("heading", { name: "Deterministic feedback" })).toBeVisible({ timeout: 60_000 });
      await expect(page.getByRole("region", { name: "Conversational ECG tutor" })).toBeVisible();
      await page.getByRole("button", { name: index === 4 ? "Finish round" : "Next ECG" }).click();
    }

    await expect(page.getByRole("heading", { name: "Rapid round debrief" })).toBeVisible();
    await expect(page.getByText(/Across this round, preserve your rhythm anchor/)).toBeVisible();
    await expect(page.getByText("Cross-concept bridge", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Train / })).toHaveAttribute("href", /\/train\?focus=/);
    expect(debriefBodies).toHaveLength(1);
    const debriefBody = debriefBodies[0];
    expect(debriefBody?.message).toContain("using only this deterministic aggregate and recent receipt sample");
    expect(debriefBody?.message).toContain("Do not add diagnoses or measurements.");
    const viewerState = debriefBodies[0]?.viewerState;
    expect(viewerState).toMatchObject({
      activity: "rapid_round_debrief",
      pace: "untimed",
      completedCaseCount: 5,
      deterministicOnly: true,
    });
    expect(Object.keys(viewerState ?? {}).sort()).toEqual([
      "activity",
      "completedCaseCount",
      "deterministicOnly",
      "pace",
      "recentDeterministicReceipts",
    ]);
    const deterministicReceipts = viewerState?.recentDeterministicReceipts ?? [];
    expect(deterministicReceipts).toHaveLength(5);
    deterministicReceipts.forEach((receipt) => {
      expect(Object.keys(receipt).sort()).toEqual([
        "caseId",
        "correct",
        "misconceptions",
        "missed",
        "overcalled",
        "responseMs",
        "score",
        "timedOut",
      ]);
      expect(receipt).not.toHaveProperty("revealedDiagnosis");
      expect(receipt).not.toHaveProperty("measurements");
    });
    expect(serverServedBeforeNext).toHaveLength(5);
    const completedCaseIds = deterministicReceipts.map((receipt) => receipt.caseId);
    expect(new Set(completedCaseIds).size).toBe(5);
    serverServedBeforeNext.forEach((served, index) => expect(served).toEqual([...new Set(completedCaseIds.slice(0, index))]));
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
