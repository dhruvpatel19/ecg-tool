import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import {
  collectConsoleErrors,
  isOpaqueEcgCapability,
  registerVerifiedE2ELearner,
  strongestWaveformPoint,
  type VerifiedE2ELearner,
} from "./helpers";

async function completeRapidSweep(page: Page, synthesis = "Evidence-limited complete ECG interpretation.") {
  const fields = [
    ["Rate", "Normal rate"],
    ["Rhythm", "Regular sinus rhythm"],
    ["Axis", "Normal axis"],
    ["Intervals", "Intervals appear normal"],
    ["QRS", "Narrow QRS / no block"],
    ["ST–T", "No acute ST–T abnormality"],
    ["Chambers", "No chamber enlargement"],
  ] as const;
  await page.getByRole("tab", { name: /Sweep/ }).click();
  for (const [step, choice] of fields) {
    await page.getByRole("button", { name: new RegExp(`^\\d+\\. ${step}`) }).click();
    await page.getByRole("button", { name: choice, exact: true }).click();
  }
  await page.getByRole("button", { name: /^8\. Synthesis/ }).click();
  await page.getByLabel("One-line synthesis", { exact: true }).fill(synthesis);
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

    await expect(page.getByRole("button", { name: /Start untimed practice|Start ward read|Start time-pressured quick-look/ })).toBeEnabled({ timeout: 30_000 });
    await expect(recovery).toHaveCount(0);
    expect(activeChecks).toBeGreaterThanOrEqual(2);
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
    await page.getByRole("button", { name: "Start untimed practice" }).click();
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
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
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
    await page.getByRole("button", { name: /Untimed practice/ }).click();
    const selectionResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/[^/]+\/next$/.test(url.pathname)
        && response.request().postDataJSON()?.activate === false;
    });
    await page.getByRole("button", { name: "Start untimed practice" }).click();
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
    await page.goto("/rapid?focus=normal_ecg&receiptConcept=integrated_interpretation&subskill=synthesize&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Dplan");
    await expect(page.getByText(/Complete-read check/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Time-pressured quick-look/ })).toBeDisabled();
    await expect(page.getByRole("button", { name: /Untimed practice/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Rapid round length")).toHaveValue("10");
    await expect(page.getByRole("link", { name: "Return to study plan" })).toHaveAttribute("href", "/profile?tab=plan");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("cross-concept launch carries the validated secondary concept into a frozen Rapid set", async ({ page }) => {
    await page.goto(
      "/rapid?focus=normal_ecg&secondaryConcept=atrial_fibrillation&receiptConcept=normal_ecg&subskill=synthesize&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Dplan",
    );

    await expect(page.getByText(/reserves two distinct unannounced ECGs/i)).toBeVisible();
    await expect(page.getByText(/Normal ECG/i).first()).toBeVisible();
    await expect(page.getByText(/Atrial fibrillation/i).first()).toBeVisible();
    await expect(page.getByText(/cross-concept comparison is formative practice/i)).toBeVisible();
    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/rapid/rounds"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start untimed practice" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({
      pace: "untimed",
      length: 10,
      focusConcept: "normal_ecg",
      secondaryConcept: "atrial_fibrillation",
      focusSubskill: "synthesize",
    });
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
  });

  test("recommended Rapid length seeds setup but an explicit learner choice owns launch", async ({ page }) => {
    await page.goto("/rapid?focus=normal_ecg&receiptConcept=normal_ecg&subskill=recognize&suggestedLength=10&pace=ward&returnTo=%2Fprofile%3Ftab%3Dplan");
    const length = page.getByLabel("Rapid round length");
    await expect(length).toHaveValue("10");
    await length.selectOption("25");

    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/rapid/rounds"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start ward read" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({ length: 25 });
  });

  test("saved Rapid setup prefills untouched controls while learner edits and complete-read safety win", async ({ page }) => {
    const saved = await page.request.put("/api/backend/learning/preferences", {
      data: { rapidPace: "emergency", defaultSessionLength: 25 },
    });
    expect(saved.ok()).toBeTruthy();

    await page.goto("/rapid");
    const emergency = page.getByRole("button", { name: /Time-pressured quick-look/ });
    await expect(emergency).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Rapid round length")).toHaveValue("25");

    const ward = page.getByRole("button", { name: /Ward read/ });
    await ward.click();
    await page.getByLabel("Rapid round length").selectOption("5");
    await page.waitForTimeout(300);
    await expect(ward).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Rapid round length")).toHaveValue("5");

    await page.goto("/rapid?focus=normal_ecg&receiptConcept=normal_ecg&subskill=synthesize&pace=emergency&suggestedLength=10");
    await expect(page.getByRole("button", { name: /Ward read/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /Time-pressured quick-look/ })).toBeDisabled();
    await expect(page.getByText(/Emergency pace was changed to Ward read because this handoff requires a complete interpretation/i)).toBeVisible();
    await expect(page.getByLabel("Rapid round length")).toHaveValue("10");
  });

  test("Ward read uses two minutes, quick sweep choices, precise fallback, and a clean 320px layout", async ({ page }) => {
    await page.goto("/rapid?pace=ward&suggestedLength=5");
    await page.getByRole("button", { name: "Start ward read" }).click();
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    const timer = page.locator(".rapid-timer");
    await expect(timer).toHaveAttribute("data-clock-state", "running", { timeout: 15_000 });
    expect(Number.parseInt((await timer.textContent()) ?? "0", 10)).toBeGreaterThanOrEqual(115);

    await page.getByRole("tab", { name: /Sweep/ }).click();
    const rateGroup = page.getByRole("group", { name: "Rate quick choices" });
    const normalRate = rateGroup.getByRole("button", { name: "Normal rate", exact: true });
    await normalRate.click();
    await expect(normalRate).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Or type a more precise entry")).toBeVisible();
    await page.getByLabel("Rate", { exact: true }).fill("72 bpm");
    await expect(normalRate).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByLabel("Rate", { exact: true })).toHaveValue("72 bpm");

    await page.setViewportSize({ width: 320, height: 800 });
    await page.waitForTimeout(200);
    const geometry = await page.evaluate(() => {
      const rail = document.querySelector<HTMLElement>(".learning-response-rail")?.getBoundingClientRect();
      const choices = [...document.querySelectorAll<HTMLElement>(".rapid-sweep-choices button")]
        .map((node) => node.getBoundingClientRect());
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        railFits: Boolean(rail && rail.left >= 0 && rail.right <= window.innerWidth + 1),
        choicesFit: choices.every((box) => box.left >= 0 && box.right <= window.innerWidth + 1),
        minimumChoiceHeight: Math.min(...choices.map((box) => box.height)),
      };
    });
    expect(geometry).toMatchObject({ documentFits: true, railFits: true, choicesFit: true });
    expect(geometry.minimumChoiceHeight).toBeGreaterThanOrEqual(44);

    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(axe.violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.map((node) => node.target),
    })), JSON.stringify(axe.violations, null, 2)).toEqual([]);
  });

  test("abandons a 5000-ECG round with confirmation and starts a smaller round at a new pace", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/rapid");

    await page.getByRole("button", { name: /Untimed practice/ }).click();
    await page.getByLabel("Rapid round length").selectOption("5000");
    const marathonStart = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/backend/rapid/rounds" && request.method() === "POST";
    });
    await page.getByRole("button", { name: "Start untimed practice" }).click();
    expect((await marathonStart).postDataJSON()).toMatchObject({ pace: "untimed", length: 5000 });
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("ECG 1 / 5000", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Abandon round" }).click();
    const confirmation = page.getByRole("alertdialog", { name: "Abandon this Rapid round?" });
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toContainText("current unsubmitted read will not be scored");
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
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible();

    await page.getByRole("button", { name: "Abandon round" }).click();
    const abandonResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/abandon$/.test(url.pathname);
    });
    await page.getByRole("button", { name: "Abandon round and change setup" }).click();
    const retired = await abandonResponse;
    expect(retired.ok()).toBeTruthy();
    expect((await retired.json()).round).toMatchObject({ status: "abandoned", length: 5000 });
    await expect(page.getByRole("heading", { name: "Rapid ECG rounds" })).toBeVisible();
    await expect(page.getByLabel("Rapid round length")).toHaveValue("5000");

    await page.getByRole("button", { name: /Time-pressured quick-look/ }).click();
    await page.getByLabel("Rapid round length").selectOption("5");
    const replacementStart = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/backend/rapid/rounds" && request.method() === "POST";
    });
    await page.getByRole("button", { name: "Start time-pressured quick-look" }).click();
    expect((await replacementStart).postDataJSON()).toMatchObject({ pace: "emergency", length: 5 });
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
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
        version: 3,
        ownerKey: owner,
        roundId: id,
        context: "",
        view: "complete",
        paceId: "untimed",
        sessionLength: 500,
        caseIndex: 499,
        currentCaseRef: null,
        sweep: { rate: "", rhythm: "", axis: "", intervals: "", conduction: "", st_t: "", chambers: "", synthesis: "" },
        selectedConcepts: [],
        confidence: 3,
        grade: null,
        aiViewerActions: [],
        traceEvidence: null,
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
        version: 3,
        ownerKey: owner,
        roundId: id,
        context: "",
        view: "complete",
        paceId: "untimed",
        sessionLength: 5,
        caseIndex: 4,
        currentCaseRef: null,
        sweep: { rate: "", rhythm: "", axis: "", intervals: "", conduction: "", st_t: "", chambers: "", synthesis: "" },
        selectedConcepts: [],
        confidence: 3,
        grade: null,
        aiViewerActions: [],
        traceEvidence: null,
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
    await expect(page.getByRole("heading", { name: "Rapid ECG rounds" })).toHaveCount(0);
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

    await page.getByRole("button", { name: /Untimed practice/ }).click();
    await page.getByRole("button", { name: "Start untimed practice" }).click();
    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
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
        const responsePanel = document.querySelector<HTMLElement>(".rapid-answer-panel")!;
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
      const stage = document.querySelector<HTMLElement>(".learning-waveform-pane .viewer-stage")?.getBoundingClientRect();
      const svgElement = document.querySelector<SVGSVGElement>(".learning-waveform-pane .viewer-stage svg");
      const svg = svgElement?.getBoundingClientRect();
      const rail = document.querySelector<HTMLElement>(".learning-response-rail")?.getBoundingClientRect();
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        svgFitsStage: Boolean(svg && stage && svg.left >= stage.left - 1 && svg.right <= stage.right + 1),
        svgTouchAction: svgElement?.style.touchAction ?? "",
        railFits: Boolean(rail && rail.left >= 0 && rail.right <= window.innerWidth + 1),
        hasAllLeadLabels: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
          .every((lead) => [...(svgElement?.querySelectorAll("text") ?? [])].some((node) => node.textContent?.trim() === lead)),
      };
    });
    expect(mobileTrace).toMatchObject({
      documentFits: true,
      svgFitsStage: true,
      svgTouchAction: "pan-x pan-y",
      railFits: true,
      hasAllLeadLabels: true,
    });

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("configures an untimed round, commits a blinded read, and shows deterministic feedback", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const liveGradeRequests: string[] = [];
    page.on("request", (request) => {
      if (/\/api\/backend\/grade\/(?:click|region)\//.test(new URL(request.url()).pathname)) {
        liveGradeRequests.push(request.url());
      }
    });
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
    const served = await roundResponse.json() as { round: { roundId: string }; current: { case: { caseId: string; displayId: string }; packet: Record<string, unknown> & {
      case_id: string;
      display_id: string;
      ptbxl_plus: { fiducials: { rois: Array<{ lead: string; concept: string; timeStartSec: number }> } };
    } } };
    const packet = served.current.packet;
    const servedEcgRef = served.current.case.caseId;
    expect(isOpaqueEcgCapability(servedEcgRef)).toBe(true);
    expect(packet.case_id === servedEcgRef).toBe(true);
    expect(served.current.case.displayId !== servedEcgRef).toBe(true);
    expect(packet.display_id !== servedEcgRef).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), servedEcgRef)).toBe(false);
    expect(packet.blinded).toBe(true);
    expect(packet).not.toHaveProperty("supported_objectives");
    expect(packet.ptbxl_plus.fiducials.rois).toEqual([]);
    const qrs = await strongestWaveformPoint(page, served.current.case.caseId, "II", 0, 10, { mode: "rapid", sessionId: served.round.roundId });

    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible();
    await expect(page.getByText("Tutor silent until commitment", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toHaveCount(0);
    await expect(page.getByRole("tablist", { name: "Rapid response steps" })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Findings/ })).toHaveAttribute("aria-selected", "true");

    await page.getByLabel("Add ECG finding").selectOption("normal_ecg");
    await expect(page.getByRole("button", { name: "Remove Normal ECG" })).toBeVisible();
    await completeRapidSweep(page, "Normal ECG pattern on rapid review.");
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.getByLabel("Keyboard task lead").selectOption("II");
    await page.getByLabel("Time cursor (seconds)").fill(qrs.timeSec.toFixed(3));
    await page.getByRole("button", { name: "Grade selected point" }).click();
    await page.getByRole("tab", { name: /Commit/ }).click();
    await expect(page.getByText("QRS mark recorded. Correctness will be revealed after commitment.")).toBeVisible();
    expect(liveGradeRequests).toEqual([]);
    await expect.poll(() => page.evaluate((expectedRef) => {
      const key = Object.keys(sessionStorage).find((candidate) => candidate.startsWith("ecg-tool:rapid-round:v2:"));
      if (!key) return false;
      const snapshot = JSON.parse(sessionStorage.getItem(key) ?? "null") as { version?: number; currentCaseRef?: string } | null;
      return snapshot?.version === 3 && snapshot.currentCaseRef === expectedRef;
    }, servedEcgRef)).toBe(true);
    const localSnapshot = await page.evaluate(() => {
      const key = Object.keys(sessionStorage).find((candidate) => candidate.startsWith("ecg-tool:rapid-round:v2:"));
      return key ? JSON.parse(sessionStorage.getItem(key) ?? "null") as Record<string, unknown> : null;
    });
    expect(localSnapshot).not.toHaveProperty("caseSummary");
    expect(localSnapshot).not.toHaveProperty("packet");
    expect(JSON.stringify(localSnapshot)).not.toContain("displayId");
    const resumedRound = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/api/backend/rapid/rounds/active"));
    await page.reload();
    const resumedPayload = await (await resumedRound).json() as { current: { case: { caseId: string }; packet: { case_id: string } } };
    expect(resumedPayload.current.case.caseId === servedEcgRef).toBe(true);
    expect(resumedPayload.current.packet.case_id === servedEcgRef).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), servedEcgRef)).toBe(false);
    await page.getByRole("tab", { name: /Sweep/ }).click();
    await page.getByRole("button", { name: /^8\. Synthesis/ }).click();
    await expect(page.getByLabel("One-line synthesis")).toHaveValue("Normal ECG pattern on rapid review.");
    await page.getByRole("tab", { name: /Findings/ }).click();
    await expect(page.getByRole("button", { name: "Remove Normal ECG" })).toBeVisible();
    await page.getByRole("tab", { name: /Commit/ }).click();
    await expect(page.getByText("QRS mark recorded. Correctness will be revealed after commitment.")).toBeVisible();
    expect(liveGradeRequests).toEqual([]);

    const tutorRestoreRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/backend/tutor/threads") && url.searchParams.get("caseId") === servedEcgRef;
    });
    const submissionRequest = page.waitForRequest((request) => /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/submit$/.test(new URL(request.url()).pathname));
    const submissionResponse = page.waitForResponse((response) => /\/api\/backend\/rapid\/rounds\/rr_[^/]+\/submit$/.test(new URL(response.url()).pathname));
    await page.getByRole("button", { name: "Commit interpretation" }).click();
    const submitBody = (await submissionRequest).postDataJSON() as { traceEvidence?: { mode?: string; point?: { lead?: string } } };
    expect(submitBody.traceEvidence).toMatchObject({ mode: "point", point: { lead: "II" } });
    const submitted = await (await submissionResponse).json() as {
      current: { packet: Record<string, unknown>; answer: { grade: { masteryDelta: Record<string, number>; legacyObjectiveMasterySuppressed: boolean } } };
      receipts: Array<{ concept: string; subskill: string; accepted: boolean }>;
    };
    const tutorRestoreUrl = new URL((await tutorRestoreRequest).url());
    expect(tutorRestoreUrl.searchParams.get("scopeKey")).toBe(`rapid:${served.round.roundId}`);
    expect(submitted.current.packet).toHaveProperty("supported_objectives");
    expect(submitted.current.answer.grade.masteryDelta).toEqual({});
    expect(submitted.current.answer.grade.legacyObjectiveMasterySuppressed).toBe(true);
    expect(submitted.receipts).toContainEqual(expect.objectContaining({ concept: "qrs_complex", subskill: "localize", accepted: true }));

    await expect(page.getByRole("heading", { name: "Case feedback" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("heading", { name: "Recognized" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
    await expect(page.locator(".learning-workspace-shell")).toHaveAttribute("data-phase", "feedback");
    await expect(page.locator(".learning-response-rail")).toHaveAttribute("data-response-phase", "feedback");
    const tutorLayer = page.locator(".learning-tutor-layer");
    await expect(tutorLayer).toHaveAttribute("data-drawer-state", "closed");
    await expect(tutorLayer).toBeHidden();
    expect(await tutorLayer.boundingBox()).toBeNull();
    const openTutor = page.getByRole("button", { name: "Open tutor" });
    await expect(openTutor).toBeVisible();
    await openTutor.click();
    const tutorDialog = page.getByRole("dialog", { name: /Rapid ECG tutor/ });
    await expect(tutorDialog).toBeVisible();
    await expect(page.getByRole("region", { name: "Conversational ECG tutor" })).toBeVisible();
    await tutorDialog.getByRole("button", { name: "Close tutor" }).click();
    await expect(tutorLayer).toBeHidden();
    await expect(openTutor).toBeFocused();
    await expect(page.getByText(/QRS localization verified on the trace/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Next ECG" })).toBeVisible();
    await page.evaluate(() => window.sessionStorage.clear());
    await page.reload();
    await expect(page.getByRole("heading", { name: "Case feedback" })).toBeVisible();
    await expect(page.getByText(/QRS localization verified on the trace/i)).toBeVisible();
    await expect(page.locator(".rapid-timer")).toHaveAttribute("data-clock-state", "complete");
    await expect(page.locator(".rapid-timer")).toHaveText("Read complete");
    await expect(page.locator(".rapid-clockbar")).toHaveCount(0);
    await expect(page.getByLabel("Committed trace proof")).toContainText(/QRS in lead II/);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("tachyarrhythmia handoff constrains the first case and preserves return navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
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
    const payload = await response.json() as Record<string, unknown>;
    expect(payload).not.toHaveProperty("targetObjectives");

    await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: "Return to lesson" })).toHaveAttribute("href", "/learn/tachyarrhythmias?scene=m06-s11");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("emergency Focus Stack includes PVC, waits for the rendered paper, and fits 390px", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route("**/api/backend/rapid/rounds/*/waveform/*?*", async (route) => {
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

    const dominant = page.getByLabel("Search one dominant ECG finding");
    await expect(page.locator(".rapid-recognition")).toHaveAttribute("data-catalog-loaded", "true");
    await dominant.fill("Premature Ventricular");
    const findingList = page.getByRole("listbox", { name: "Filtered ECG findings" });
    await expect(findingList).toBeVisible();
    await expect(findingList.getByRole("option", { name: "Premature Ventricular Complex" })).toBeVisible();
    await dominant.press("Enter");
    await expect(page.getByText("Selected: Premature Ventricular Complex")).toBeVisible();
    await expect(dominant).toHaveAttribute("aria-expanded", "false");
    const commit = page.getByRole("button", { name: "Commit interpretation" });
    await expect(dominant).toBeVisible();
    await expect(commit).toBeVisible();
    await expect(commit).toBeEnabled();

    const geometry = await page.evaluate(() => {
      const select = document.querySelector<HTMLInputElement>('input[aria-label="Search one dominant ECG finding"]');
      const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent?.includes("Commit interpretation"));
      const waveform = document.querySelector<HTMLElement>(".learning-waveform-pane")?.getBoundingClientRect();
      const rail = document.querySelector<HTMLElement>(".learning-response-rail")?.getBoundingClientRect();
      const stage = document.querySelector<HTMLElement>(".learning-waveform-pane .viewer-stage")?.getBoundingClientRect();
      const svgElement = document.querySelector<SVGSVGElement>(".learning-waveform-pane .viewer-stage svg");
      const svg = svgElement?.getBoundingClientRect();
      const selectBox = select?.getBoundingClientRect();
      const buttonBox = button?.getBoundingClientRect();
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        selectFits: Boolean(selectBox && selectBox.left >= 0 && selectBox.right <= window.innerWidth),
        buttonFits: Boolean(buttonBox && buttonBox.left >= 0 && buttonBox.right <= window.innerWidth),
        selectInVisualViewport: Boolean(selectBox && selectBox.top >= 0 && selectBox.bottom <= window.innerHeight),
        buttonInVisualViewport: Boolean(buttonBox && buttonBox.top >= 0 && buttonBox.bottom <= window.innerHeight),
        submitWidth: buttonBox?.width ?? 0,
        waveformFirst: Boolean(waveform && rail && waveform.top < rail.top),
        waveformFits: Boolean(waveform && waveform.left >= 0 && waveform.right <= window.innerWidth),
        railFits: Boolean(rail && rail.left >= 0 && rail.right <= window.innerWidth),
        railWidth: rail?.width ?? 0,
        sessionPosition: getComputedStyle(document.querySelector<HTMLElement>(".learning-session-bar")!).position,
        responsePosition: getComputedStyle(document.querySelector<HTMLElement>(".rapid-answer-panel")!).position,
        svgFitsStage: Boolean(svg && stage && svg.left >= stage.left - 1 && svg.right <= stage.right + 1),
        svgTouchAction: svgElement?.style.touchAction ?? "",
        hasAllLeadLabels: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
          .every((lead) => [...(svgElement?.querySelectorAll("text") ?? [])].some((node) => node.textContent?.trim() === lead)),
      };
    });
    expect(geometry.documentFits).toBe(true);
    expect(geometry.selectFits).toBe(true);
    expect(geometry.buttonFits).toBe(true);
    expect(geometry.selectInVisualViewport).toBe(true);
    expect(geometry.buttonInVisualViewport).toBe(true);
    expect(geometry.submitWidth).toBeLessThan(390);
    expect(geometry.waveformFirst).toBe(true);
    expect(geometry.waveformFits).toBe(true);
    expect(geometry.railFits).toBe(true);
    expect(geometry.railWidth).toBeLessThanOrEqual(358);
    expect(geometry.sessionPosition).toBe("sticky");
    expect(geometry.responsePosition).toBe("static");
    expect(geometry.svgFitsStage).toBe(true);
    expect(geometry.svgTouchAction).toBe("auto");
    expect(geometry.hasAllLeadLabels).toBe(true);

    await commit.click();
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
    let latestQrs: { lead: string; timeSec: number; amplitudeMv: number } | null = null;
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (!response.ok() || !/\/api\/backend\/rapid\/rounds\/rr_[^/]+\/next$/.test(url.pathname)) return;
      const requestBody = response.request().postDataJSON() as { activate?: boolean };
      if (requestBody.activate) return;
      const selection = await response.json() as {
        round?: { roundId?: string; servedCount?: number; recentServed?: string[] };
        current?: { case?: { caseId?: string }; packet?: { ptbxl_plus?: { fiducials?: { rois?: unknown[] } } } };
      };
      if (!selection.current?.case?.caseId) return;
      expect(selection.current?.packet?.ptbxl_plus?.fiducials?.rois ?? []).toEqual([]);
      if (!selection.round?.roundId) return;
      latestQrs = await strongestWaveformPoint(page, selection.current.case.caseId, "II", 0, 10, { mode: "rapid", sessionId: selection.round.roundId });
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
    await page.getByRole("button", { name: /Untimed practice/ }).click();
    await page.getByLabel("Rapid round length").selectOption("5");
    await page.getByRole("button", { name: "Start untimed practice" }).click();

    for (let index = 0; index < 5; index += 1) {
      await expect(page.getByRole("heading", { name: "What matters on this ECG?" })).toBeVisible({ timeout: 30_000 });
      await expect.poll(() => latestQrs, { timeout: 15_000 }).not.toBeNull();
      const tracePoint = latestQrs!;
      latestQrs = null;
      await page.getByText("Keyboard / precise-entry alternative").click();
      await page.getByLabel("Keyboard task lead").selectOption(tracePoint.lead);
      await page.getByLabel("Time cursor (seconds)").fill(tracePoint.timeSec.toFixed(3));
      await page.getByRole("button", { name: "Grade selected point" }).click();
      await expect(page.getByText("Point recorded. Correctness will be revealed after you commit your response.")).toBeVisible();
      await page.getByLabel("Add ECG finding").selectOption("normal_ecg");
      await completeRapidSweep(page, "Systematic rapid read committed for deterministic review.");
      await page.getByRole("tab", { name: /Commit/ }).click();
      await page.getByRole("button", { name: "Commit interpretation" }).click();
      await expect(page.getByRole("heading", { name: "Case feedback" })).toBeVisible({ timeout: 60_000 });
      await expect(page.getByRole("button", { name: "Open tutor" })).toBeVisible();
      await page.getByRole("button", { name: index === 4 ? "Finish round" : "Next ECG" }).click();
    }

    await expect(page.getByRole("heading", { name: "Rapid round review" })).toBeVisible();
    await expect(page.getByText(/Across this round, preserve your rhythm anchor/)).toBeVisible();
    await expect(page.getByText("Connect this skill", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Train / })).toHaveAttribute("href", /\/train\?focus=/);
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
