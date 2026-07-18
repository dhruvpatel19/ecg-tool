import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page, type Route } from "@playwright/test";
import {
  collectConsoleErrors,
  isOpaqueEcgCapability,
  registerVerifiedE2ELearner,
  type VerifiedE2ELearner,
} from "./helpers";

async function chooseRoundLength(page: Page, length: 5 | 10 | 20) {
  await page.getByLabel("Rapid round length").getByRole("button", { name: new RegExp(`^${length}\\s*ECGs$`, "i") }).click();
}

async function startQuickUntimedRound(page: Page) {
  await page.getByRole("button", { name: /Quick recognition/ }).click();
  await page.getByRole("button", { name: /No timer/ }).click();
  await chooseRoundLength(page, 5);
  await page.getByRole("button", { name: "Start rapid set" }).click();
}

async function answerOneQuestionDeck(page: Page, answer = "normal ECG") {
  await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Your answer", { exact: true }).fill(answer);
  await page.getByRole("button", { name: "Submit answers" }).click();
}

async function injectTaskPacket(route: Route, taskPacket: Record<string, unknown>) {
  const response = await route.fetch();
  const payload = await response.json() as {
    current?: { kind?: string; taskPacket?: Record<string, unknown> | null } | null;
  };
  if (payload.current?.kind === "pending") payload.current.taskPacket = taskPacket;
  await route.fulfill({ response, json: payload });
}

test.describe("Mode 3 · Rapid", () => {
  let rapidLearner: VerifiedE2ELearner;

  test.beforeEach(async ({ page }) => {
    rapidLearner = await registerVerifiedE2ELearner(page, { prefix: "rapid" });
  });

  test("shows and retries a failed saved-round check instead of silently exposing setup", async ({ page }) => {
    let activeChecks = 0;
    let allowRecovery = false;
    await page.route("**/api/backend/rapid/rounds/active", async (route) => {
      activeChecks += 1;
      if (!allowRecovery) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporarily unavailable" }) });
        return;
      }
      await route.fulfill({ json: { round: null, current: null } });
    });

    await page.goto("/rapid");
    const recovery = page.getByRole("alert").filter({ hasText: /Rapid practice is temporarily unavailable/i });
    await expect(recovery).toBeVisible();
    allowRecovery = true;
    await recovery.getByRole("button", { name: "Retry saved round check" }).click();

    await expect(page.getByRole("button", { name: "Start rapid set" })).toBeEnabled({ timeout: 30_000 });
    await expect(recovery).toHaveCount(0);
    expect(activeChecks).toBeGreaterThanOrEqual(2);
  });

  test("does not silently replace a targeted recommendation with an unrelated saved round", async ({ page }) => {
    const started = await page.request.post("/api/backend/rapid/rounds", {
      data: {
        learnerId: "demo",
        pace: "untimed",
        length: 5,
        focusConcept: "normal_ecg",
        focusSubskill: "recognize",
        contextKey: "?focus=normal_ecg&receiptConcept=normal_ecg&subskill=recognize",
        exclusions: [],
      },
    });
    expect(started.ok()).toBeTruthy();
    expect((await started.json()).round.receiptConcept).toBe("normal_ecg");

    await page.goto("/rapid?focus=atrial_fibrillation&receiptConcept=atrial_fibrillation&subskill=recognize&returnTo=%2Fhome%3Fpanel%3Dplan");
    const conflict = page.getByRole("alert").filter({ hasText: "saved Rapid round for Normal ECG" });
    await expect(conflict).toContainText("The recommended Atrial fibrillation check was not substituted into it.");
    await expect(page.getByText(/This round starts with.*Atrial fibrillation/i)).toHaveCount(0);
  });

  test("keeps a failed ECG selection recoverable and nonduplicated on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    let allowCase = false;
    await page.route("**/api/backend/rapid/rounds/*/next", async (route) => {
      if (!allowCase) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "ECG selection temporarily unavailable" }) });
        return;
      }
      await route.continue();
    });

    await page.goto("/rapid?pace=untimed&suggestedLength=5");
    await page.getByRole("button", { name: "Start rapid set" }).click();
    const alert = page.getByRole("alert").filter({ hasText: /ECG selection temporarily unavailable/i });
    await expect(alert).toBeVisible();
    await expect(page.getByText("Your round is still saved. Retry this ECG when the connection returns.", { exact: true })).toBeVisible();
    await expect(page.locator(".rapid-loading")).not.toContainText("ECG selection temporarily unavailable");

    const retry = page.getByRole("button", { name: "Retry ECG" });
    const box = await retry.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

    allowCase = true;
    await retry.click();
    await expect(page.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 30_000 });
    await expect(alert).toHaveCount(0);
  });

  test("retries a failed scoped waveform without exposing its ECG capability", async ({ page }) => {
    let allowWaveform = false;
    await page.route("**/api/backend/rapid/rounds/*/waveform/*?*", async (route) => {
      if (!allowWaveform) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "waveform temporarily unavailable" }) });
        return;
      }
      await route.continue();
    });

    await page.goto("/rapid");
    await page.getByRole("button", { name: /No timer/ }).click();
    const selectionResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    await page.getByRole("button", { name: "Start rapid set" }).click();
    const selection = await (await selectionResponse).json() as { round: { roundId: string }; current: { case: { caseId: string } } };
    const ecgRef = selection.current.case.caseId;
    expect(isOpaqueEcgCapability(ecgRef)).toBe(true);

    const viewer = page.getByRole("region", { name: "Rapid ECG waveform" });
    await expect(viewer.getByText("This ECG could not be loaded.")).toBeVisible({ timeout: 30_000 });
    expect(await page.locator("body").evaluate((body, capability) => body.innerHTML.includes(capability), ecgRef)).toBe(false);

    allowWaveform = true;
    const retryResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname === `/api/backend/rapid/rounds/${selection.round.roundId}/waveform/${encodeURIComponent(ecgRef)}`
    ));
    await viewer.getByRole("button", { name: "Retry ECG" }).click();
    expect((await retryResponse).ok()).toBeTruthy();
    await expect(viewer.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
  });

  test("synthesis handoff exposes only complete-read paces and the exact receipt gate", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/rapid?focus=normal_ecg&receiptConcept=integrated_interpretation&subskill=synthesize&suggestedLength=10&returnTo=%2Fhome%3Fpanel%3Dplan");
    await expect(page.getByRole("button", { name: /Complete interpretation/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /Speed round/ })).toBeDisabled();
    await expect(page.getByRole("button", { name: /No timer/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Rapid round length").getByRole("button", { name: /^10\s*ECGs$/i })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("link", { name: "Return to study plan" })).toHaveAttribute("href", "/home?panel=plan");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("cross-concept launch carries the validated secondary concept into a frozen Rapid set", async ({ page }) => {
    await page.goto(
      "/rapid?focus=normal_ecg&secondaryConcept=atrial_fibrillation&receiptConcept=normal_ecg&subskill=synthesize&suggestedLength=10&returnTo=%2Fhome%3Fpanel%3Dplan",
    );

    await expect(page.getByText(/reserves two distinct unannounced ECGs/i)).toBeVisible();
    await expect(page.getByText(/Normal ECG/i).first()).toBeVisible();
    await expect(page.getByText(/Atrial fibrillation/i).first()).toBeVisible();
    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/rapid/rounds"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start rapid set" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({
      pace: "untimed",
      length: 10,
      contractVersion: "mixed-v2",
      questionDepth: "complete",
      focusConcept: "normal_ecg",
      secondaryConcept: "atrial_fibrillation",
      focusSubskill: "synthesize",
    });
    await expect(page.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 30_000 });
  });

  test("recommended Rapid length seeds setup but an explicit learner choice owns launch", async ({ page }) => {
    await page.goto("/rapid?focus=normal_ecg&receiptConcept=normal_ecg&subskill=recognize&suggestedLength=10&pace=ward&returnTo=%2Fhome%3Fpanel%3Dplan");
    const lengths = page.getByLabel("Rapid round length");
    await expect(lengths.getByRole("button", { name: /^10\s*ECGs$/i })).toHaveAttribute("aria-pressed", "true");
    await chooseRoundLength(page, 20);

    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/rapid/rounds"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start rapid set" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({ contractVersion: "mixed-v2", length: 20 });
    await expect(page.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: "Return to study plan" })).toHaveCount(0);
    const returnButton = page.getByRole("button", { name: "Return to study plan" });
    await returnButton.click();
    const confirmation = page.getByRole("alertdialog", { name: "Leave this Rapid round?" });
    await expect(confirmation).toBeVisible();
    await confirmation.getByRole("button", { name: "Keep practicing" }).click();
    await expect(confirmation).toHaveCount(0);
    await expect(returnButton).toBeFocused();

    await returnButton.click();
    const abandonResponse = page.waitForResponse((response) => (
      /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/abandon$/.test(new URL(response.url()).pathname)
    ));
    await confirmation.getByRole("button", { name: "Return to study plan and abandon round" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page).toHaveURL(/\/home\?panel=plan$/);
  });

  test("saved Rapid setup prefills untouched controls while learner edits and complete-read safety win", async ({ page }) => {
    const saved = await page.request.put("/api/backend/learning/preferences", {
      data: { rapidPace: "emergency", defaultSessionLength: 25 },
    });
    expect(saved.ok()).toBeTruthy();

    await page.goto("/rapid");
    const emergency = page.getByRole("button", { name: /Speed round/ });
    await expect(emergency).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Rapid round length").getByRole("button", { name: /^20\s*ECGs$/i })).toHaveAttribute("aria-pressed", "true");

    const ward = page.getByRole("button", { name: /Standard timer/ });
    await ward.click();
    await chooseRoundLength(page, 5);
    await page.waitForTimeout(300);
    await expect(ward).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Rapid round length").getByRole("button", { name: /^5\s*ECGs$/i })).toHaveAttribute("aria-pressed", "true");

    await page.goto("/rapid?focus=normal_ecg&receiptConcept=normal_ecg&subskill=synthesize&pace=emergency&suggestedLength=10");
    await expect(page.getByRole("button", { name: /Standard timer/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /Speed round/ })).toBeDisabled();
    await expect(page.getByText(/Speed round was changed to Standard timer because this handoff requires a complete interpretation/i)).toBeVisible();
    await expect(page.getByLabel("Rapid round length").getByRole("button", { name: /^10\s*ECGs$/i })).toHaveAttribute("aria-pressed", "true");
  });

  test("offers an adaptive or mixed plan, three read depths, realistic timing, and only learner-scale lengths", async ({ page }) => {
    await page.goto("/rapid");

    await expect(page.getByRole("heading", { name: "Choose how you want to read" })).toBeVisible();
    const adaptive = page.getByRole("button", { name: /Adaptive practice/ });
    const mixed = page.getByRole("button", { name: /Mixed practice/ });
    await expect(adaptive).toHaveAttribute("aria-pressed", "true");
    await mixed.click();
    await page.getByRole("button", { name: /Quick recognition/ }).click();
    await page.getByRole("button", { name: /No timer/ }).click();
    await chooseRoundLength(page, 10);

    const lengths = page.getByLabel("Rapid round length").getByRole("button");
    await expect(lengths).toHaveCount(3);
    await expect(page.getByRole("button", { name: /Focused read/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Complete interpretation/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Standard timer/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Speed round/ })).toBeVisible();
    await expect(page.getByText(/5000/)).toHaveCount(0);

    const selectionResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/rapid/rounds"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start rapid set" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({
      contractVersion: "mixed-v2",
      practiceMode: "mixed",
      questionDepth: "quick",
      pace: "untimed",
      length: 10,
    });
    const selected = await (await selectionResponse).json() as {
      current: { taskPacket?: Record<string, unknown> & { tasks?: Array<Record<string, unknown>> } };
    };
    expect(selected.current.taskPacket).toMatchObject({
      version: "rapid-task-packet-v1",
      tasks: [expect.objectContaining({ type: "short_answer", required: true })],
    });
    expect(selected.current.taskPacket?.tasks).toHaveLength(1);
    expect(JSON.stringify(selected.current.taskPacket)).not.toMatch(/grading|correctOptionId|expectedValue|supported_objectives/i);

    await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("tablist", { name: "Rapid response steps" })).toHaveCount(0);
    await expect(page.getByLabel("Confidence")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Commit interpretation" })).toHaveCount(0);

    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(axe.violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.map((node) => node.target),
    })), JSON.stringify(axe.violations, null, 2)).toEqual([]);
  });

  test("renders mixed typed, choice, measurement, and ECG-localization prompts one at a time", async ({ page }) => {
    await page.route("**/api/backend/rapid/rounds/*/next", async (route) => {
      if (route.request().postDataJSON()?.activate !== false) {
        await route.continue();
        return;
      }
      await injectTaskPacket(route, {
        version: "rapid-task-packet-v1",
        display: { kind: "rhythm_strip", leads: ["II", "V1"] },
        estimatedSeconds: 180,
        tasks: [
          { id: "task_short", type: "short_answer", prompt: "Name the dominant rhythm.", placeholder: "Use one concise phrase", bloomLevel: "apply", skillId: "recognize", required: true },
          { id: "task_choice", type: "single_choice", prompt: "Which conduction finding is best supported?", bloomLevel: "analyze", skillId: "discriminate", required: true, options: [
            { id: "option_1", label: "Right bundle branch block" },
            { id: "option_2", label: "Left bundle branch block" },
            { id: "option_3", label: "Nonspecific intraventricular delay" },
            { id: "option_4", label: "Ventricular pre-excitation" },
          ] },
          { id: "task_numeric", type: "numeric_fill_in", prompt: "Estimate the ventricular rate.", unit: "bpm", placeholder: "Enter one number", bloomLevel: "apply", skillId: "measure", required: true },
          { id: "task_point", type: "point_localization", prompt: "Place one point directly on a QRS complex.", bloomLevel: "apply", skillId: "localize", required: true },
        ],
      });
    });

    await page.goto("/rapid");
    await page.getByRole("button", { name: /Complete interpretation/ }).click();
    await page.getByRole("button", { name: /No timer/ }).click();
    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/rapid/rounds"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start rapid set" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({
      contractVersion: "mixed-v2",
      questionDepth: "complete",
      pace: "untimed",
    });

    await expect(page.getByText("Question 1 of 4", { exact: true })).toBeVisible({ timeout: 30_000 });
    const rhythmStrip = page.getByRole("img", { name: "Interactive rhythm strips for II, V1" });
    await expect(page.getByRole("region", { name: "Interactive ECG rhythm strips" })).toBeVisible();
    await expect(rhythmStrip).toBeVisible();
    await expect(page.getByRole("img", { name: /standard 12-lead ECG/i })).toHaveCount(0);
    await page.getByLabel("Your answer", { exact: true }).fill("Atrial fibrillation");
    await page.getByRole("button", { name: /^Next/ }).click();
    await page.getByRole("radio", { name: /Right bundle branch block/ }).click();
    await page.getByRole("button", { name: /^Next/ }).click();
    await page.getByLabel("Your measurement").fill("145");
    await page.getByRole("button", { name: /^Next/ }).click();
    await expect(page.getByText("Use the active trace tool", { exact: true })).toBeVisible();
    await expect(page.getByText("Make the requested selection directly on the ECG.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit answers" })).toBeDisabled();
    await expect(page.getByRole("tablist", { name: "Rapid response steps" })).toHaveCount(0);
    await expect(page.getByLabel("Confidence")).toHaveCount(0);
  });

  test("abandons a 20-ECG round with confirmation and starts a five-ECG speed round", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/rapid");

    await page.getByRole("button", { name: /No timer/ }).click();
    await chooseRoundLength(page, 20);
    const longStart = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/backend/rapid/rounds" && request.method() === "POST";
    });
    await page.getByRole("button", { name: "Start rapid set" }).click();
    expect((await longStart).postDataJSON()).toMatchObject({ contractVersion: "mixed-v2", pace: "untimed", length: 20 });
    await expect(page.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("ECG 1 / 20", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Abandon round" }).click();
    const confirmation = page.getByRole("alertdialog", { name: "Abandon this Rapid round?" });
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toContainText("No ECG from this round has been submitted, so the round will not appear in learning history.");
    await expect(confirmation).toContainText("current unsubmitted ECG will be discarded and will not be scored or count toward progress");
    const keepPracticing = confirmation.getByRole("button", { name: "Keep practicing" });
    const confirmButton = confirmation.getByRole("button", { name: "Abandon round and change setup" });
    await expect(keepPracticing).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(confirmButton).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(keepPracticing).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(confirmation).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Abandon round" })).toBeFocused();
    await expect(page.getByText(/Question 1 of \d+/)).toBeVisible();

    await page.getByRole("button", { name: "Abandon round" }).click();
    const abandonResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/abandon$/.test(url.pathname);
    });
    await page.getByRole("button", { name: "Abandon round and change setup" }).click();
    const retired = await abandonResponse;
    expect(retired.ok()).toBeTruthy();
    expect((await retired.json()).round).toMatchObject({ status: "abandoned", length: 20 });
    await expect(page.getByRole("heading", { name: "Choose how you want to read" })).toBeVisible();
    await expect(page.getByLabel("Rapid round length").getByRole("button", { name: /^20\s*ECGs$/i })).toHaveAttribute("aria-pressed", "true");

    await page.getByRole("button", { name: /Quick recognition/ }).click();
    await page.getByRole("button", { name: /Speed round/ }).click();
    await chooseRoundLength(page, 5);
    const replacementStart = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/backend/rapid/rounds" && request.method() === "POST";
    });
    await page.getByRole("button", { name: "Start rapid set" }).click();
    expect((await replacementStart).postDataJSON()).toMatchObject({ contractVersion: "mixed-v2", questionDepth: "quick", pace: "emergency", length: 5 });
    await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("ECG 1 / 5", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Abandon round" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("reloads a completed long round from its authoritative full result ledger", async ({ page }) => {
    const roundId = "rr_completed_restore";
    const ownerKey = rapidLearner.user.userId;
    const result = (index: number) => ({
      caseId: `ec_test_capability_${index}`,
      score: index % 2 ? 1 : 0,
      timedOut: false,
      responseMs: 1_000 + index,
      correctObjectives: index % 2 ? ["sinus_rhythm"] : [],
      missedObjectives: index % 2 ? [] : ["sinus_rhythm"],
      overcalledObjectives: [],
      misconceptions: [],
      revealedDiagnosis: index % 2 ? "Sinus rhythm" : "Review sinus rhythm",
    });
    const fullResults = Array.from({ length: 500 }, (_, index) => result(index + 1));
    const recoveryTail = fullResults.slice(-100);

    await page.addInitScript(({ id, tail, owner }) => {
      window.sessionStorage.setItem(`ecg-tool:rapid-round:v2:${owner}`, JSON.stringify({
        version: 4,
        ownerKey: owner,
        roundId: id,
        context: "",
        view: "complete",
        paceId: "untimed",
        practiceMode: "adaptive",
        questionDepth: "focused",
        sessionLength: 500,
        caseIndex: 499,
        currentCaseRef: null,
        sweep: { rate: "", rhythm: "", axis: "", intervals: "", conduction: "", st_t: "", chambers: "", synthesis: "" },
        selectedConcepts: [],
        confidence: 3,
        grade: null,
        aiViewerActions: [],
        traceEvidence: null,
        taskResponses: {},
        activeTaskIndex: 0,
        traceReceipt: "",
        handoffReceipt: "",
        results: tail,
        startedAtEpochMs: null,
        deadlineAtEpochMs: null,
      }));
    }, { id: roundId, tail: recoveryTail, owner: ownerKey });
    await page.route("**/api/backend/rapid/rounds/active", (route) => route.fulfill({
      json: { round: null, current: null, results: [], resultCount: 0, resultsTruncated: false },
    }));
    await page.route(`**/api/backend/rapid/rounds/${roundId}/results?*`, (route) => route.fulfill({
      json: { roundId, offset: 0, limit: 5000, total: 500, results: fullResults },
    }));
    await page.route("**/api/backend/tutor/message", (route) => route.fulfill({
      json: {
        threadId: "restored-rapid-round",
        tutorMessage: "The complete server-owned round is ready for review.",
        feedback: "",
        viewerActions: [],
        objectiveUpdates: [],
        misconceptions: [],
        uncertaintyWarnings: [],
        suggestedNextStep: "Review the complete pattern.",
        socraticQuestion: "Which finding changed most across the full round?",
        citedEvidence: ["500 committed Rapid results"],
        onLessonTopic: true,
      },
    }));

    const fullLedgerRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === `/api/backend/rapid/rounds/${roundId}/results`
    ));
    await page.goto("/rapid");
    await fullLedgerRequest;
    await expect(page.getByRole("heading", { name: "Rapid round review" })).toBeVisible();
    await expect(page.getByText("500/500", { exact: true })).toBeVisible();
    await expect(page.getByText("Showing the most recent 50 of 500 ECGs.", { exact: false })).toBeVisible();
    await expect(page.getByText("The complete server-owned round is ready for review.")).toBeVisible();
  });

  test("preserves a read-only cached completed review when the result ledger is offline", async ({ page }) => {
    const roundId = "rr_completed_offline";
    const ownerKey = rapidLearner.user.userId;
    const cachedResults = [4, 5].map((index) => ({
      caseId: `ec_test_capability_${index}`,
      score: index === 5 ? 1 : 0,
      timedOut: false,
      responseMs: 1_000 + index,
      correctObjectives: index === 5 ? ["sinus_rhythm"] : [],
      missedObjectives: index === 5 ? [] : ["sinus_rhythm"],
      overcalledObjectives: [],
      misconceptions: [],
      revealedDiagnosis: index === 5 ? "Sinus rhythm" : "Review sinus rhythm",
    }));
    await page.addInitScript(({ id, results, owner }) => {
      window.sessionStorage.setItem(`ecg-tool:rapid-round:v2:${owner}`, JSON.stringify({
        version: 4,
        ownerKey: owner,
        roundId: id,
        context: "",
        view: "complete",
        paceId: "untimed",
        practiceMode: "adaptive",
        questionDepth: "focused",
        sessionLength: 5,
        caseIndex: 4,
        currentCaseRef: null,
        sweep: { rate: "", rhythm: "", axis: "", intervals: "", conduction: "", st_t: "", chambers: "", synthesis: "" },
        selectedConcepts: [],
        confidence: 3,
        grade: null,
        aiViewerActions: [],
        traceEvidence: null,
        taskResponses: {},
        activeTaskIndex: 0,
        traceReceipt: "",
        handoffReceipt: "",
        results,
        startedAtEpochMs: null,
        deadlineAtEpochMs: null,
      }));
    }, { id: roundId, results: cachedResults, owner: ownerKey });
    await page.route("**/api/backend/rapid/rounds/active", (route) => route.fulfill({
      json: { round: null, current: null, results: [], resultCount: 0, resultsTruncated: false },
    }));
    await page.route(`**/api/backend/rapid/rounds/${roundId}/results?*`, (route) => route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "offline" }),
    }));

    await page.goto("/rapid");

    await expect(page.getByRole("heading", { name: "Rapid round review" })).toBeVisible();
    await expect(page.getByText("Cached review · full ledger temporarily unavailable")).toBeVisible();
    await expect(page.getByText("5/5", { exact: true })).toBeVisible();
    await expect(page.getByText("ECG 4", { exact: true })).toBeVisible();
    await expect(page.getByText("ECG 5", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Choose how you want to read" })).toHaveCount(0);
  });

  test("ECG-first workspace dominates at 1440, 1280, and 1024 with a focus-aware compact nav", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/rapid");

    const nav = page.locator(".side-nav");
    await expect(nav).toHaveAttribute("data-learning-route", "rapid");
    await expect(page.getByText("AI coach ready", { exact: true })).toHaveCount(0);
    await expect.poll(async () => (await nav.boundingBox())?.width ?? 999).toBeLessThanOrEqual(80);
    const rapidNavLink = page.getByRole("link", { name: "Rapid practice" });
    await rapidNavLink.focus();
    await expect.poll(async () => (await nav.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(250);
    await page.locator("#main-content").focus();
    await expect.poll(async () => (await nav.boundingBox())?.width ?? 999).toBeLessThanOrEqual(80);

    await startQuickUntimedRound(page);
    await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    const shell = page.locator(".learning-workspace-shell");
    await expect(shell).toHaveAttribute("data-phase", "response");
    await expect(page.locator(".learning-response-rail")).toHaveAttribute("data-response-phase", "response");
    await expect(page.locator(".learning-tutor-layer")).toHaveCount(0);

    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1280, height: 800 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(200);
      const geometry = await page.evaluate(() => {
        const box = (selector: string) => document.querySelector<HTMLElement>(selector)?.getBoundingClientRect();
        const session = box(".learning-session-bar");
        const body = box(".learning-workspace-body");
        const waveform = box(".learning-waveform-pane");
        const rail = box(".learning-response-rail");
        const disclosure = box(".learning-disclosure-area");
        const responseRail = document.querySelector<HTMLElement>(".learning-response-rail")!;
        const responsePanel = document.querySelector<HTMLElement>(".rapid-task-deck")!;
        const responseStyle = getComputedStyle(responseRail);
        return {
          documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
          sessionPosition: getComputedStyle(document.querySelector<HTMLElement>(".learning-session-bar")!).position,
          bodyFits: Boolean(body && body.left >= 0 && body.right <= window.innerWidth + 1),
          waveformWidth: waveform?.width ?? 0,
          railWidth: rail?.width ?? 0,
          waveformBeforeRail: Boolean(waveform && rail && waveform.left < rail.left),
          railBottom: rail?.bottom ?? Number.POSITIVE_INFINITY,
          responseOverflow: responseStyle.overflowY,
          railContentFits: responseRail.scrollWidth <= responseRail.clientWidth + 1,
          panelContentFits: responsePanel.scrollWidth <= responsePanel.clientWidth + 1,
          disclosureHeight: disclosure?.height ?? Number.POSITIVE_INFINITY,
          sessionTop: session?.top ?? -1,
        };
      });
      expect(geometry.documentFits).toBe(true);
      expect(geometry.sessionPosition).toBe("sticky");
      expect(geometry.sessionTop).toBeGreaterThanOrEqual(0);
      expect(geometry.bodyFits).toBe(true);
      expect(geometry.railWidth).toBeGreaterThanOrEqual(350);
      expect(geometry.railWidth).toBeLessThanOrEqual(365);
      expect(geometry.waveformWidth).toBeGreaterThan(geometry.railWidth);
      expect(geometry.waveformBeforeRail).toBe(true);
      expect(geometry.railBottom).toBeLessThanOrEqual(viewport.height + 2);
      expect(geometry.responseOverflow).toBe("auto");
      expect(geometry.railContentFits).toBe(true);
      expect(geometry.panelContentFits).toBe(true);
      expect(geometry.disclosureHeight).toBeLessThanOrEqual(70);
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(200);
    const mobileTrace = await page.evaluate(() => {
      const stageElement = document.querySelector<HTMLElement>(".learning-waveform-pane .viewer-stage");
      const stage = stageElement?.getBoundingClientRect();
      const svgElement = document.querySelector<SVGSVGElement>(".learning-waveform-pane .viewer-stage svg");
      const svg = svgElement?.getBoundingClientRect();
      const rail = document.querySelector<HTMLElement>(".learning-response-rail")?.getBoundingClientRect();
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        paperWidth: svg?.width ?? 0,
        stageWidth: stage?.width ?? 0,
        stageScrolls: Boolean(stageElement && stageElement.scrollWidth > stageElement.clientWidth + 100),
        stageOverflowX: stageElement ? getComputedStyle(stageElement).overflowX : "",
        svgTouchAction: svgElement?.style.touchAction ?? "",
        railFits: Boolean(rail && rail.left >= 0 && rail.right <= window.innerWidth + 1),
        hasAllLeadLabels: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
          .every((lead) => [...(svgElement?.querySelectorAll("text") ?? [])].some((node) => node.textContent?.trim() === lead)),
      };
    });
    expect(mobileTrace).toMatchObject({
      documentFits: true,
      svgTouchAction: "pan-x pan-y",
      railFits: true,
      hasAllLeadLabels: true,
    });
    expect(mobileTrace.paperWidth).toBeGreaterThanOrEqual(700);
    expect(mobileTrace.paperWidth).toBeGreaterThan(mobileTrace.stageWidth * 1.5);
    expect(mobileTrace.stageScrolls).toBe(true);
    expect(mobileTrace.stageOverflowX).toMatch(/auto|scroll/);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keeps a mixed-v2 one-question draft blinded, owner-bound, restorable, and server-graded", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const liveGradeRequests: string[] = [];
    page.on("request", (request) => {
      if (/\/api\/backend\/grade\/(?:click|region)\//.test(new URL(request.url()).pathname)) liveGradeRequests.push(request.url());
    });
    await page.goto("/rapid?focus=normal_ecg&receiptConcept=normal_ecg&subskill=recognize");

    const noTimer = page.getByRole("button", { name: /No timer/ });
    await page.getByRole("button", { name: /Quick recognition/ }).click();
    await noTimer.click();
    await expect(noTimer).toHaveAttribute("aria-pressed", "true");

    const servedRound = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    await page.getByRole("button", { name: "Start rapid set" }).click();
    const roundResponse = await servedRound;
    expect(roundResponse.ok()).toBeTruthy();
    const served = await roundResponse.json() as {
      round: { roundId: string };
      current: {
        case: { caseId: string; displayId: string };
        packet: Record<string, unknown> & { case_id: string; display_id: string; ptbxl_plus: { fiducials: { rois: unknown[] } } };
        taskPacket: { version: string; tasks: Array<{ id: string; type: string; prompt: string }> };
      };
    };
    const { packet, taskPacket } = served.current;
    const servedEcgRef = served.current.case.caseId;
    const taskId = taskPacket.tasks[0].id;
    expect(isOpaqueEcgCapability(servedEcgRef)).toBe(true);
    expect(packet.case_id).toBe(servedEcgRef);
    expect(served.current.case.displayId).not.toBe(servedEcgRef);
    expect(packet.display_id).not.toBe(servedEcgRef);
    expect(packet.blinded).toBe(true);
    expect(packet).not.toHaveProperty("supported_objectives");
    expect(packet.ptbxl_plus.fiducials.rois).toEqual([]);
    expect(taskPacket).toMatchObject({ version: "rapid-task-packet-v1", tasks: [{ type: "short_answer" }] });
    expect(JSON.stringify(taskPacket)).not.toMatch(/grading|correctOptionId|expectedValue|supportedAnswer/i);

    await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("img", { name: /12-lead ECG|ECG/i })).toBeVisible();
    await expect(page.getByText("Tutor silent until commitment", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toHaveCount(0);
    await page.getByLabel("Your answer", { exact: true }).fill("normal ECG");
    expect(liveGradeRequests).toEqual([]);

    await expect.poll(() => page.evaluate(({ expectedRef, expectedTask }) => {
      const key = Object.keys(sessionStorage).find((candidate) => candidate.startsWith("ecg-tool:rapid-round:v2:"));
      if (!key) return false;
      const snapshot = JSON.parse(sessionStorage.getItem(key) ?? "null") as {
        version?: number;
        currentCaseRef?: string;
        taskResponses?: Record<string, unknown>;
      } | null;
      return snapshot?.version === 4
        && snapshot.currentCaseRef === expectedRef
        && snapshot.taskResponses?.[expectedTask] === "normal ECG";
    }, { expectedRef: servedEcgRef, expectedTask: taskId })).toBe(true);
    const localSnapshot = await page.evaluate(() => {
      const key = Object.keys(sessionStorage).find((candidate) => candidate.startsWith("ecg-tool:rapid-round:v2:"));
      return key ? JSON.parse(sessionStorage.getItem(key) ?? "null") as Record<string, unknown> : null;
    });
    expect(localSnapshot).not.toHaveProperty("caseSummary");
    expect(localSnapshot).not.toHaveProperty("packet");
    expect(localSnapshot).not.toHaveProperty("taskPacket");
    expect(JSON.stringify(localSnapshot)).not.toContain("displayId");

    const resumedRound = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/api/backend/rapid/rounds/active"));
    await page.reload();
    const resumedPayload = await (await resumedRound).json() as { current: { case: { caseId: string }; packet: { case_id: string } } };
    expect(resumedPayload.current.case.caseId).toBe(servedEcgRef);
    expect(resumedPayload.current.packet.case_id).toBe(servedEcgRef);
    await expect(page.getByLabel("Your answer", { exact: true })).toHaveValue("normal ECG");
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), servedEcgRef)).toBe(false);

    const tutorRestoreRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/backend/tutor/threads") && url.searchParams.get("caseId") === servedEcgRef;
    });
    const submissionRequest = page.waitForRequest((request) => /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/submit$/.test(new URL(request.url()).pathname));
    const submissionResponse = page.waitForResponse((response) => /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/submit$/.test(new URL(response.url()).pathname));
    await page.getByRole("button", { name: "Submit answers" }).click();
    const submitBody = (await submissionRequest).postDataJSON() as { taskResponses?: Record<string, unknown>; traceEvidence?: unknown };
    expect(submitBody.taskResponses).toEqual({ [taskId]: "normal ECG" });
    expect(submitBody.traceEvidence ?? null).toBeNull();
    const submitted = await (await submissionResponse).json() as {
      current: { packet: Record<string, unknown>; answer: { grade: { taskFeedback?: unknown[] } } };
      receipts: Array<{ concept: string; subskill: string; accepted: boolean }>;
    };
    const tutorRestoreUrl = new URL((await tutorRestoreRequest).url());
    expect(tutorRestoreUrl.searchParams.get("scopeKey")).toBe(`rapid:${served.round.roundId}`);
    expect(submitted.current.packet).toHaveProperty("supported_objectives");
    expect(submitted.current.answer.grade.taskFeedback).toHaveLength(1);
    expect(submitted.receipts).toContainEqual(expect.objectContaining({ subskill: "recognize", accepted: true }));

    await expect(page.getByRole("heading", { name: "Case feedback" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("Question 1", { exact: true })).toBeVisible();
    await expect(page.getByText("Supported answer", { exact: true })).toBeVisible();
    await expect(page.locator(".learning-workspace-shell")).toHaveAttribute("data-phase", "feedback");
    await expect(page.locator(".learning-response-rail")).toHaveAttribute("data-response-phase", "feedback");
    const tutorLayer = page.locator(".learning-tutor-layer");
    await expect(tutorLayer).toHaveAttribute("data-drawer-state", "closed");
    await expect(tutorLayer).toBeHidden();
    const openTutor = page.getByRole("button", { name: "Open tutor" });
    await openTutor.click();
    const tutorDialog = page.getByRole("dialog", { name: /Rapid ECG tutor/ });
    await expect(tutorDialog.getByRole("region", { name: "Debrief · post-commit chat" })).toBeVisible();
    await tutorDialog.getByRole("button", { name: "Close tutor" }).click();
    await expect(openTutor).toBeFocused();

    await page.evaluate(() => window.sessionStorage.clear());
    await page.reload();
    await expect(page.getByRole("heading", { name: "Case feedback" })).toBeVisible();
    await expect(page.locator(".rapid-timer")).toHaveAttribute("data-clock-state", "complete");
    await expect(page.locator(".rapid-timer")).toHaveText("Read complete");
    await expect(page.locator(".rapid-clockbar")).toHaveCount(0);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("preserves a server-echoed numeric response in post-commit feedback", async ({ page }) => {
    let taskId = "";
    let submittedValue: unknown;
    const numericTaskPacket = {
      version: "rapid-task-packet-v1",
      display: { kind: "twelve_lead" },
      estimatedSeconds: 45,
      tasks: [{
        id: "",
        type: "numeric_fill_in",
        prompt: "Estimate the ventricular rate.",
        unit: "bpm",
        minValue: 20,
        maxValue: 250,
        step: 5,
        responseLabel: "Your measurement",
        required: true,
      }],
    };

    await page.route("**/api/backend/rapid/rounds/*/next", async (route) => {
      if (route.request().postDataJSON()?.activate !== false) {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const payload = await response.json() as {
        current?: { kind?: string; taskPacket?: { tasks?: Array<{ id?: string }> } | null } | null;
      };
      taskId = payload.current?.taskPacket?.tasks?.[0]?.id ?? "";
      expect(taskId).not.toBe("");
      numericTaskPacket.tasks[0].id = taskId;
      if (payload.current?.kind === "pending") payload.current.taskPacket = numericTaskPacket;
      await route.fulfill({ response, json: payload });
    });

    await page.route("**/api/backend/rapid/rounds/*/submit", async (route) => {
      const requestBody = route.request().postDataJSON() as {
        taskResponses?: Record<string, unknown>;
      };
      submittedValue = requestBody.taskResponses?.[taskId];

      // The live server still owns its original frozen task in this browser-only
      // regression. Forward a valid response for that task, then reproduce the
      // numeric response shape the server returns for a real measurement task.
      const forwardedBody = {
        ...requestBody,
        taskResponses: { [taskId]: String(submittedValue) },
      };
      const response = await route.fetch({ postData: JSON.stringify(forwardedBody) });
      const payload = await response.json() as {
        current?: {
          taskPacket?: unknown;
          answer?: {
            response?: { taskResponses?: Record<string, unknown> };
            grade?: Record<string, unknown>;
          } | null;
        } | null;
      };
      expect(response.ok()).toBeTruthy();
      expect(payload.current?.answer).toBeTruthy();
      payload.current!.taskPacket = numericTaskPacket;
      payload.current!.answer!.response = {
        ...(payload.current!.answer!.response ?? {}),
        taskResponses: { [taskId]: submittedValue },
      };
      payload.current!.answer!.grade = {
        ...(payload.current!.answer!.grade ?? {}),
        score: 0,
        taskFeedback: [{
          taskId,
          type: "numeric_fill_in",
          complete: true,
          correct: false,
          score: 0,
          timedOut: false,
          formativeOnly: false,
          expectedValue: 64,
          tolerance: 5,
          unit: "bpm",
          feedback: "Recheck the ECG-grid calculation.",
        }],
      };
      await route.fulfill({ response, json: payload });
    });

    await page.goto("/rapid");
    await startQuickUntimedRound(page);
    await expect(page.getByText("Estimate the ventricular rate.", { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("Your measurement").fill("80");
    await page.getByRole("button", { name: "Submit answers" }).click();

    expect(submittedValue).toBe(80);
    const feedback = page.locator(".rapid-task-feedback-list article").first();
    await expect(feedback).toBeVisible({ timeout: 60_000 });
    await expect(feedback.getByText("80 bpm", { exact: true })).toBeVisible();
    await expect(feedback.getByText("64 bpm", { exact: true })).toBeVisible();
    await expect(feedback.getByText("No answer", { exact: true })).toHaveCount(0);
  });

  test("tachyarrhythmia handoff constrains the first case and preserves return navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/rapid?focus=tachyarrhythmia_mixed&subskill=recognize&returnTo=/learn/tachyarrhythmias?scene=m06-s11");
    await page.getByRole("button", { name: /Quick recognition/ }).click();
    await page.getByRole("button", { name: /No timer/ }).click();

    const targeted = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    await page.getByRole("button", { name: "Start rapid set" }).click();
    const response = await targeted;
    expect(response.ok()).toBeTruthy();
    const payload = await response.json() as Record<string, unknown>;
    expect(payload).not.toHaveProperty("targetObjectives");

    await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: "Return to lesson" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Return to lesson" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("a speed round starts only after the paper is rendered and keeps full-scale ECG paper scrollable at 390px", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route("**/api/backend/rapid/rounds/*/waveform/*?*", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1_200));
      await route.continue();
    });
    await page.goto("/rapid?focus=premature_ventricular_complex&subskill=recognize");
    await page.getByRole("button", { name: /Quick recognition/ }).click();
    await page.getByRole("button", { name: /Speed round/ }).click();
    await page.getByRole("button", { name: "Start rapid set" }).click();

    await expect(page.getByText("Question 1 of 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    const timer = page.locator(".rapid-timer");
    await expect(timer).toHaveAttribute("data-clock-state", "waiting");
    await expect(timer).toHaveText("ECG loading");
    await expect(page.getByLabel("Your answer", { exact: true })).toBeDisabled();
    await expect(timer).toHaveAttribute("data-clock-state", "running", { timeout: 10_000 });
    const startingSeconds = Number.parseInt((await timer.textContent()) ?? "0", 10);
    expect(startingSeconds).toBeGreaterThanOrEqual(23);

    const answer = page.getByLabel("Your answer", { exact: true });
    await expect(answer).toBeEnabled();
    await answer.fill("premature ventricular complex");
    const submit = page.getByRole("button", { name: "Submit answers" });
    await expect(submit).toBeEnabled();
    await expect(page.getByLabel("Search one dominant ECG finding")).toHaveCount(0);

    const geometry = await page.evaluate(() => {
      const waveform = document.querySelector<HTMLElement>(".learning-waveform-pane")?.getBoundingClientRect();
      const rail = document.querySelector<HTMLElement>(".learning-response-rail")?.getBoundingClientRect();
      const stageElement = document.querySelector<HTMLElement>(".learning-waveform-pane .viewer-stage");
      const stage = stageElement?.getBoundingClientRect();
      const svgElement = document.querySelector<SVGSVGElement>(".learning-waveform-pane .viewer-stage svg");
      const svg = svgElement?.getBoundingClientRect();
      const taskDeck = document.querySelector<HTMLElement>(".rapid-task-deck")?.getBoundingClientRect();
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        waveformFirst: Boolean(waveform && rail && waveform.top < rail.top),
        waveformFits: Boolean(waveform && waveform.left >= 0 && waveform.right <= window.innerWidth),
        railFits: Boolean(rail && rail.left >= 0 && rail.right <= window.innerWidth),
        railWidth: rail?.width ?? 0,
        taskDeckFits: Boolean(taskDeck && taskDeck.left >= 0 && taskDeck.right <= window.innerWidth),
        sessionPosition: getComputedStyle(document.querySelector<HTMLElement>(".learning-session-bar")!).position,
        paperWidth: svg?.width ?? 0,
        stageWidth: stage?.width ?? 0,
        stageScrolls: Boolean(stageElement && stageElement.scrollWidth > stageElement.clientWidth + 100),
        stageOverflowX: stageElement ? getComputedStyle(stageElement).overflowX : "",
        svgTouchAction: svgElement?.style.touchAction ?? "",
        hasAllLeadLabels: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
          .every((lead) => [...(svgElement?.querySelectorAll("text") ?? [])].some((node) => node.textContent?.trim() === lead)),
      };
    });
    expect(geometry.documentFits).toBe(true);
    expect(geometry.waveformFirst).toBe(true);
    expect(geometry.waveformFits).toBe(true);
    expect(geometry.railFits).toBe(true);
    expect(geometry.railWidth).toBeLessThanOrEqual(358);
    expect(geometry.taskDeckFits).toBe(true);
    expect(geometry.sessionPosition).toBe("sticky");
    expect(geometry.paperWidth).toBeGreaterThanOrEqual(700);
    expect(geometry.paperWidth).toBeGreaterThan(geometry.stageWidth * 1.5);
    expect(geometry.stageScrolls).toBe(true);
    expect(geometry.stageOverflowX).toMatch(/auto|scroll/);
    expect(geometry.svgTouchAction).toBe("pan-x pan-y");
    expect(geometry.hasAllLeadLabels).toBe(true);

    await submit.click();
    const openTutor = page.getByRole("button", { name: "Open tutor" });
    await expect(openTutor).toBeVisible({ timeout: 60_000 });
    await openTutor.click();
    const tutor = page.getByRole("dialog", { name: /Rapid ECG tutor/ });
    await expect(tutor).toBeVisible();
    const drawerBox = await tutor.boundingBox();
    expect(drawerBox?.x).toBeGreaterThanOrEqual(0);
    expect((drawerBox?.x ?? 0) + (drawerBox?.width ?? 0)).toBeLessThanOrEqual(390);
    await page.keyboard.press("Escape");
    await expect(tutor).toBeHidden();
    await expect(openTutor).toBeFocused();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("automatically requests an owner-bound server-grounded AI debrief", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    type RapidDebriefBody = {
      message?: string;
      caseId?: string | null;
      viewerState?: { activity?: string };
      rapidRoundContext?: {
        roundId?: string;
        answerCount?: number;
        version?: string;
      };
    };
    const debriefBodies: RapidDebriefBody[] = [];
    const serverServedBeforeNext: string[][] = [];
    const selectedCaseIds: string[] = [];
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (!response.ok() || !/\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)) return;
      const requestBody = response.request().postDataJSON() as { activate?: boolean };
      if (requestBody.activate) return;
      const selection = await response.json() as {
        round?: { roundId?: string; servedCount?: number; recentServed?: string[] };
        current?: {
          case?: { caseId?: string };
          packet?: { ptbxl_plus?: { fiducials?: { rois?: unknown[] } } };
          taskPacket?: { tasks?: Array<Record<string, unknown>> };
        };
      };
      if (!selection.current?.case?.caseId) return;
      expect(selection.current?.packet?.ptbxl_plus?.fiducials?.rois ?? []).toEqual([]);
      if (!selection.round?.roundId) return;
      expect(selection.current.taskPacket?.tasks).toHaveLength(1);
      expect(JSON.stringify(selection.current.taskPacket)).not.toMatch(/grading|correctOptionId|expectedValue/i);
      selectedCaseIds.push(selection.current.case.caseId);
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
    await startQuickUntimedRound(page);

    for (let index = 0; index < 5; index += 1) {
      await answerOneQuestionDeck(page, "normal ECG");
      await expect(page.getByRole("heading", { name: "Case feedback" })).toBeVisible({ timeout: 60_000 });
      await expect(page.getByRole("button", { name: "Open tutor" })).toBeVisible();
      await page.getByRole("button", { name: index === 4 ? "Finish round" : "Next ECG" }).click();
    }

    await expect(page.getByRole("heading", { name: "Rapid round review" })).toBeVisible();
    await expect(page.getByText(/Across this round, preserve your rhythm anchor/)).toBeVisible();
    await expect(page.getByText("Connect this skill", { exact: true })).toBeVisible();
    const remediationHref = await page.getByRole("link", { name: /^Train / }).getAttribute("href");
    expect(remediationHref).toBeTruthy();
    const remediationUrl = new URL(remediationHref!, "http://localhost");
    expect(remediationUrl.pathname).toBe("/train");
    expect(Object.fromEntries(remediationUrl.searchParams)).toEqual({
      concept: "axis_normal",
      receiptConcept: "axis_normal",
      subskill: "recognize",
      returnTo: "/rapid",
    });
    expect(debriefBodies).toHaveLength(1);
    const debriefBody = debriefBodies[0];
    expect(debriefBody?.message).toBe("Debrief this completed Rapid ECG round from its server-owned record.");
    expect(debriefBody?.message).not.toContain("Aggregate:");
    expect(debriefBody?.message).not.toContain("Recent sample:");
    expect(debriefBody?.caseId).toBeNull();
    const viewerState = debriefBodies[0]?.viewerState;
    expect(viewerState).toEqual({ activity: "rapid_round_debrief" });
    expect(debriefBody?.rapidRoundContext).toEqual({
      roundId: expect.stringMatching(/^rr_/),
      answerCount: 5,
      version: "rapid-round-debrief-v1",
    });
    expect(serverServedBeforeNext).toHaveLength(5);
    const completedCaseIds = selectedCaseIds;
    expect(new Set(completedCaseIds).size).toBe(5);
    serverServedBeforeNext.forEach((served, index) => expect(served).toEqual([...new Set(completedCaseIds.slice(0, index))]));
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
