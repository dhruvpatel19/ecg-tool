import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import {
  collectConsoleErrors,
  isOpaqueEcgCapability,
  registerVerifiedE2ELearner,
  strongestWaveformPoint,
} from "./helpers";

test.describe("Mode 4 · Clinical Decisions", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "clinical" });
  });

  test("announces and retries a failed saved-session check in place", async ({ page }) => {
    let activeChecks = 0;
    let allowRecovery = false;
    await page.route("**/api/backend/clinical/shift/active", async (route) => {
      activeChecks += 1;
      if (!allowRecovery) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporarily unavailable" }) });
        return;
      }
      await route.fulfill({ json: { session: null, current: null, state: "picker" } });
    });

    await page.goto("/practice");
    const retry = page.getByRole("button", { name: "Retry saved session check" });
    const recovery = page.getByRole("alert").filter({ has: retry });
    await expect(recovery).toBeVisible();
    allowRecovery = true;
    await retry.click();

    await expect(page.getByRole("button", { name: "Start learning set" })).toBeEnabled({ timeout: 30_000 });
    await expect(recovery).toHaveCount(0);
    expect(activeChecks).toBeGreaterThanOrEqual(2);
  });

  test("retries a failed session-scoped waveform without rendering its capability", async ({ page }) => {
    let allowWaveform = false;
    await page.route("**/api/backend/clinical/shift/*/waveform/*?*", async (route) => {
      if (!allowWaveform) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "waveform temporarily unavailable" }) });
        return;
      }
      await route.continue();
    });

    await page.goto("/practice");
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start learning set" }).click();
    const started = await (await startResponse).json() as { session: { sessionId: string }; next: { item: { ecg_ref: string } } };
    const ecgRef = started.next.item.ecg_ref;
    expect(isOpaqueEcgCapability(ecgRef)).toBe(true);

    const viewer = page.getByRole("region", { name: "Clinical ECG waveform" });
    await expect(viewer.getByText("This ECG could not be loaded.")).toBeVisible({ timeout: 30_000 });
    expect(await page.locator("body").evaluate((body, capability) => body.innerHTML.includes(capability), ecgRef)).toBe(false);

    allowWaveform = true;
    const retryResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname === `/api/backend/clinical/shift/${started.session.sessionId}/waveform/${encodeURIComponent(ecgRef)}`
    ));
    await viewer.getByRole("button", { name: "Retry ECG" }).click();
    expect((await retryResponse).ok()).toBeTruthy();
    await expect(viewer.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
  });

  test("study-plan handoff is labeled accurately and an external return is discarded", async ({ page }) => {
    await page.goto("/practice?focus=atrial_fibrillation&subskill=apply_in_context&returnTo=%2Fprofile%3Ftab%3Dplan");
    await expect(page.getByRole("link", { name: "Return to study plan" })).toHaveAttribute("href", "/profile?tab=plan");
    await expect(page.getByText(/From your study plan: apply/i)).toBeVisible();

    await page.goto("/practice?focus=atrial_fibrillation&subskill=apply_in_context&returnTo=https%3A%2F%2Fevil.test%2Fsteal");
    await expect(page.getByRole("link", { name: /^Return to/ })).toHaveCount(0);
  });

  test("abandons a 10-case learning set with confirmation and restarts a shorter set", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/");
    await page.goto("/practice");
    await expect(page.getByRole("heading", { name: /Use the ECG to make the next decision/ })).toBeVisible();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "10 cases" }).click();
    const largeStart = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/clinical/shift/start"
    ));
    await page.getByRole("button", { name: "Start learning set" }).click();
    expect((await largeStart).postDataJSON()).toMatchObject({ lane: "clinic", tier: "learn", length: 10 });
    await expect(page.getByText("Case 1 / 10", { exact: true })).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: "Abandon learning set", exact: true }).click();
    const confirmation = page.getByRole("alertdialog", { name: "Abandon this Clinical learning set?" });
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toHaveAttribute("aria-modal", "true");
    await expect(confirmation.getByRole("button", { name: "Keep working" })).toBeFocused();
    await expect(confirmation).toContainText("Completed case answers and saved progress stay");
    await expect(confirmation).toContainText("current unsubmitted response");
    await expect(confirmation).toContainText("setting, mode, and length choices will remain selected");
    await page.keyboard.press("Escape");
    await expect(confirmation).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Abandon learning set", exact: true })).toBeFocused();

    await page.getByRole("button", { name: "Abandon learning set", exact: true }).click();
    await confirmation.getByRole("button", { name: "Keep working" }).click();
    await expect(confirmation).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Abandon learning set", exact: true })).toBeFocused();
    await expect(page.getByText("Case 1 / 10", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Abandon learning set", exact: true }).click();
    const abandonResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/cs_[^/]+\/abandon$/.test(path);
    });
    await page.getByRole("button", { name: "Abandon learning set and change setup" }).click();
    const retired = await abandonResponse;
    expect(retired.ok()).toBeTruthy();
    expect((await retired.json()).session).toMatchObject({
      status: "abandoned",
      requestedLength: 10,
      pendingItemId: null,
      feedbackItemId: null,
    });

    await expect(page.getByRole("heading", { name: /Use the ECG to make the next decision/ })).toBeVisible();
    await expect(page.getByText(/Completed cases stay in your history/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Clinic", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Learn (untimed)" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "10 cases" })).toHaveAttribute("aria-pressed", "true");
    const activeAfterAbandon = await page.request.get("/api/backend/clinical/shift/active");
    expect((await activeAfterAbandon.json()).session).toBeNull();

    await page.getByRole("button", { name: "5 cases" }).click();
    const shortStart = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/clinical/shift/start"
    ));
    await page.getByRole("button", { name: "Start learning set" }).click();
    expect((await shortStart).postDataJSON()).toMatchObject({ lane: "clinic", tier: "learn", length: 5 });
    await expect(page.getByText("Case 1 / 5", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Abandon learning set", exact: true })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keeps one ECG workspace while first look, decision, and feedback swap in the rail", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/practice?focus=qtc_prolongation");
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "Start learning set" }).click();

    const shell = page.locator('[data-learning-workspace="true"]');
    const sessionBar = page.locator(".clinical-session-bar");
    const waveform = page.getByRole("region", { name: "Clinical ECG waveform" });
    const disclosure = page.locator(".clinical-disclosure");
    await expect(shell).toHaveAttribute("data-phase", "orient", { timeout: 30_000 });
    await expect(page.getByRole("complementary", { name: "Clinical first look" })).toHaveAttribute("data-response-phase", "orient");

    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1280, height: 800 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
      const response = page.getByRole("complementary", { name: "Clinical first look" });
      const [waveformBox, responseBox, disclosureBox] = await Promise.all([
        waveform.boundingBox(),
        response.boundingBox(),
        disclosure.boundingBox(),
      ]);
      expect(waveformBox).not.toBeNull();
      expect(responseBox).not.toBeNull();
      expect(disclosureBox).not.toBeNull();
      expect(responseBox!.width).toBeGreaterThanOrEqual(350);
      expect(responseBox!.width).toBeLessThanOrEqual(365);
      expect(waveformBox!.width).toBeGreaterThan(responseBox!.width);
      expect(waveformBox!.x).toBeLessThan(responseBox!.x);
      expect(waveformBox!.y + waveformBox!.height).toBeLessThanOrEqual(viewport.height + 1);
      expect(responseBox!.y + responseBox!.height).toBeLessThanOrEqual(viewport.height + 1);
      expect(disclosureBox!.height).toBeLessThanOrEqual(70);
      await expect(response).toHaveCSS("overflow-y", "auto");
      await expect(sessionBar).toHaveCSS("position", "sticky");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    }

    const orientWaveformBox = await waveform.boundingBox();
    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();
    await expect(shell).toHaveAttribute("data-phase", "decide");
    await expect(page.getByRole("complementary", { name: "Clinical first look" })).toHaveCount(0);
    const decisionRail = page.getByRole("complementary", { name: "Clinical context and decision" });
    await expect(decisionRail).toHaveAttribute("data-response-phase", "decide");
    await expect(page.getByRole("region", { name: "Clinical context and decision prompt" })).toBeFocused();
    const decisionWaveformBox = await waveform.boundingBox();
    expect(decisionWaveformBox?.x).toBe(orientWaveformBox?.x);
    expect(decisionWaveformBox?.width).toBe(orientWaveformBox?.width);

    const options = page.locator(".clinical-options").getByRole("button");
    await expect(options.first()).toBeVisible();
    await options.first().click();
    await page.getByRole("button", { name: "Commit decision", exact: true }).click();
    await expect(shell).toHaveAttribute("data-phase", "feedback", { timeout: 30_000 });
    await expect(decisionRail).toHaveCount(0);
    const feedbackRail = page.getByRole("complementary", { name: "Clinical feedback" });
    await expect(feedbackRail).toHaveAttribute("data-response-phase", "feedback");

    const tutorLayer = page.locator(".learning-tutor-layer");
    const tutorTrigger = page.getByRole("button", { name: "Open tutor" });
    const tutorDialog = page.getByRole("dialog", { name: "Case tutor" });
    await expect(tutorTrigger).toHaveAttribute("aria-expanded", "false");
    expect(await tutorLayer.boundingBox()).toBeNull();
    await tutorTrigger.click();
    await expect(tutorDialog).toBeVisible();
    await expect(tutorDialog.getByRole("button", { name: "Close tutor" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    expect(await tutorDialog.evaluate((dialog) => dialog.contains(document.activeElement))).toBeTruthy();
    await page.keyboard.press("Escape");
    await expect(tutorDialog).toBeHidden();
    await expect(tutorTrigger).toBeFocused();

    await page.setViewportSize({ width: 390, height: 844 });
    const [mobileWaveform, mobileFeedback] = await Promise.all([waveform.boundingBox(), feedbackRail.boundingBox()]);
    expect(mobileWaveform).not.toBeNull();
    expect(mobileFeedback).not.toBeNull();
    expect(mobileWaveform!.y).toBeLessThan(mobileFeedback!.y);
    expect(mobileWaveform!.width).toBeLessThanOrEqual(358);
    expect(mobileFeedback!.width).toBeLessThanOrEqual(358);
    await expect(feedbackRail).toHaveCSS("position", "static");
    await expect(feedbackRail).toHaveCSS("overflow-y", "visible");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keeps the timed first-look dock reachable with the full ECG at both mobile acceptance sizes", async ({ page }) => {
    test.setTimeout(90_000);
    const viewports = [
      { width: 320, height: 780 },
      { width: 390, height: 844 },
    ];
    const errors = collectConsoleErrors(page);
    await page.setViewportSize(viewports[0]);
    await page.goto("/practice");
    await page.getByRole("button", { name: "Shift (timed)" }).click();
    const startResponse = page.waitForResponse((response) => (
      response.url().endsWith("/api/backend/clinical/shift/start")
    ));
    await page.getByRole("button", { name: "Start shift" }).click();
    const startedResponse = await startResponse;
    expect(startedResponse.ok()).toBeTruthy();
    const started = await startedResponse.json() as {
      session: { sessionId: string };
      next: { item: { ecg_ref: string } };
    };
    expect(isOpaqueEcgCapability(started.next.item.ecg_ref)).toBe(true);

    const shell = page.locator('.clinical-runner-timed[data-phase="orient"]');
    const sessionBar = page.locator(".clinical-session-bar");
    const clock = page.locator('.clinical-clock[data-clock-phase="orient"]');
    const waveform = page.getByRole("region", { name: "Clinical ECG waveform" });
    const stage = page.getByRole("region", { name: "Scrollable ECG tracing" });
    const firstLook = page.getByRole("complementary", { name: "Clinical first look" });
    const dominantFinding = page.getByLabel("Dominant finding");
    const confidence = page.getByRole("group", { name: "First-look confidence" });
    const commit = page.getByRole("button", { name: /Commit first look and reveal context/ });

    await expect(shell).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible();
    await expect(clock.locator("span").last()).not.toHaveText("0s");
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => window.scrollTo(0, 0));
      await waveform.evaluate((element) => { element.scrollTop = 0; });
      for (const [name, element] of Object.entries({
        sessionBar,
        clock,
        waveform,
        firstLook,
        dominantFinding,
        confidence,
        commit,
      })) {
        await expect(element, `${name} should be visible at ${viewport.width}x${viewport.height}`).toBeVisible();
        const box = await element.boundingBox();
        expect(box, `${name} should have a layout box`).not.toBeNull();
        expect(box!.y, `${name} should begin inside the viewport`).toBeGreaterThanOrEqual(0);
        expect(box!.y + box!.height, `${name} should end inside the viewport`).toBeLessThanOrEqual(viewport.height + 1);
        expect(box!.x, `${name} should begin inside the viewport width`).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width, `${name} should end inside the viewport width`).toBeLessThanOrEqual(viewport.width + 1);
      }

      const [waveformBox, dockBox] = await Promise.all([
        waveform.boundingBox(),
        firstLook.boundingBox(),
      ]);
      expect(waveformBox).not.toBeNull();
      expect(dockBox).not.toBeNull();
      expect(waveformBox!.height).toBeGreaterThanOrEqual(176);
      expect(waveformBox!.y + waveformBox!.height).toBeLessThanOrEqual(dockBox!.y + 1);
      await expect(waveform).toHaveCSS("overflow-y", "auto");
      await expect(firstLook).toHaveCSS("position", "relative");

      const waveformReach = await waveform.evaluate((element) => {
        const stageElement = element.querySelector<HTMLElement>(".viewer-stage");
        return {
          clientHeight: element.clientHeight,
          scrollHeight: element.scrollHeight,
          stageClientWidth: stageElement?.clientWidth ?? 0,
          stageScrollWidth: stageElement?.scrollWidth ?? 0,
        };
      });
      expect(waveformReach.scrollHeight).toBeGreaterThan(waveformReach.clientHeight);
      expect(waveformReach.stageScrollWidth).toBeGreaterThan(waveformReach.stageClientWidth);

      await dominantFinding.focus();
      await page.keyboard.press("ArrowDown");
      await expect(dominantFinding).not.toHaveValue("");
      const medium = confidence.getByRole("button", { name: "Medium" });
      await medium.focus();
      await page.keyboard.press("Space");
      await expect(medium).toHaveAttribute("aria-pressed", "true");
      await expect(commit).toBeEnabled();
      await commit.focus();
      await expect(commit).toBeFocused();
      expect(await page.evaluate(() => window.scrollY)).toBe(0);

      const internalScroll = await waveform.evaluate((element) => {
        element.scrollTop = element.scrollHeight;
        return element.scrollTop;
      });
      expect(internalScroll).toBeGreaterThan(0);
      await stage.focus();
      await expect(stage).toBeFocused();
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    }
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("refresh restores the owned pending item, context, feedback, and report", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/");
    const startedResponse = await page.request.post("/api/backend/clinical/shift/start", {
      data: { lane: "clinic", tier: "shift", length: 1, focus: "qtc_prolongation" },
    });
    expect(startedResponse.ok()).toBeTruthy();
    const started = await startedResponse.json() as { session: { sessionId: string }; next: { itemId: string; item: { ecg_ref: string } } };
    expect(isOpaqueEcgCapability(started.next.item.ecg_ref)).toBe(true);

    await page.goto("/practice");
    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Case 1 / 1", { exact: true })).toBeVisible();
    await expect(page.locator(".clinical-context-mask")).toBeVisible();
    await expect.poll(async () => {
      const response = await page.request.get("/api/backend/clinical/shift/active");
      const body = await response.json() as { current?: { clock?: { orientDeadlineAt?: string | null } } };
      return body.current?.clock?.orientDeadlineAt ?? null;
    }).not.toBeNull();
    const orientActive = await page.request.get("/api/backend/clinical/shift/active");
    const orientBody = await orientActive.json() as { state: string; current: { itemId: string; clock: { orientDeadlineAt: string } } };
    expect(orientBody.state).toBe("orient");
    expect(orientBody.current.itemId).toBe(started.next.itemId);
    const orientDeadline = orientBody.current.clock.orientDeadlineAt;

    const resumedWaveform = page.waitForResponse((response) => (
      new URL(response.url()).pathname.includes(`/api/backend/clinical/shift/${started.session.sessionId}/waveform/`)
    ));
    await page.reload();
    expect((await resumedWaveform).ok()).toBeTruthy();
    await expect(page.getByText("Case 1 / 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".clinical-context-mask")).toBeVisible();
    const resumedOrient = await (await page.request.get("/api/backend/clinical/shift/active")).json() as { current: { item: { ecg_ref: string }; clock: { orientDeadlineAt: string } } };
    expect(resumedOrient.current.item.ecg_ref === started.next.item.ecg_ref).toBe(true);
    expect(resumedOrient.current.clock.orientDeadlineAt).toBe(orientDeadline);
    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();
    await expect(page.locator(".clinical-stem")).toBeVisible();
    const contextState = await (await page.request.get("/api/backend/clinical/shift/active")).json() as { current: { clock: { decideDeadlineAt: string } } };
    const decideDeadline = contextState.current.clock.decideDeadlineAt;
    expect(decideDeadline).toBeTruthy();

    await page.reload();
    await expect(page.locator(".clinical-stem")).toBeVisible({ timeout: 30_000 });
    const decideActive = await page.request.get("/api/backend/clinical/shift/active");
    const decideBody = await decideActive.json() as { state: string; current: { itemId: string; contextRevealed: boolean } };
    expect(decideBody.state).toBe("decide");
    expect(decideBody.current.itemId).toBe(started.next.itemId);
    expect(decideBody.current.contextRevealed).toBe(true);
    const resumedDecide = await (await page.request.get("/api/backend/clinical/shift/active")).json() as { current: { clock: { decideDeadlineAt: string } } };
    expect(resumedDecide.current.clock.decideDeadlineAt).toBe(decideDeadline);

    const options = page.locator(".clinical-options").getByRole("button");
    await expect(options.first()).toBeVisible();
    await options.first().click();
    await page.locator(".clinical-confidence").getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: "Commit decision", exact: true }).click();
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toBeVisible({ timeout: 30_000 });

    await page.reload();
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Finish shift" })).toBeVisible();
    const reportResponse = page.waitForResponse((response) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/report$/.test(new URL(response.url()).pathname)
      && response.ok()
    ));
    const shiftDebriefRequest = page.waitForRequest((request) => {
      if (!request.url().endsWith("/api/backend/tutor/message")) return false;
      const body = request.postDataJSON() as { clinicalShiftContext?: unknown };
      return Boolean(body.clinicalShiftContext);
    });
    await page.getByRole("button", { name: "Finish shift" }).click();
    const reportBody = await (await reportResponse).json() as {
      tutorContext: { contextId: string; sessionId: string; answerCount: number; version: string };
      performanceDomains: Record<string, unknown>;
      debrief: {
        clinicalEvidence: string;
        nextCaseProposal: { href: string; learningEvidence: string } | null;
      };
    };
    const debriefBody = (await shiftDebriefRequest).postDataJSON() as {
      clinicalShiftContext: typeof reportBody.tutorContext;
      lessonId: string;
      viewerState: Record<string, unknown>;
    };
    expect(debriefBody.clinicalShiftContext).toEqual(reportBody.tutorContext);
    expect(debriefBody.lessonId).toBe(reportBody.tutorContext.contextId);
    expect(debriefBody.viewerState).toEqual({ activity: "clinical_shift_debrief", committed: true });
    expect(debriefBody.viewerState).not.toHaveProperty("completedCases");
    expect(debriefBody.viewerState).not.toHaveProperty("mastery");
    expect(reportBody.debrief.clinicalEvidence).toBe("formative_only");
    expect(reportBody.debrief.nextCaseProposal?.learningEvidence).toBe("formative_only");
    expect(Object.keys(reportBody.performanceDomains).sort()).toEqual([
      "clinicalApplicationDecision",
      "confidenceCalibration",
      "ecgRecognitionFirstLook",
      "safety",
    ]);
    await expect(page.getByText("Shift complete", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What this shift actually checked" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "ECG recognition / first look" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Clinical application / decision" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Safety", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Confidence calibration" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Choose the next useful move" })).toBeVisible();
    await expect(page.getByText(/Clinical cases remain formative|cross-concept claim is withheld/i)).toBeVisible();
    if (reportBody.debrief.nextCaseProposal) {
      await expect(page.getByRole("link", { name: /Apply .* in a new case/ })).toHaveAttribute(
        "href",
        reportBody.debrief.nextCaseProposal.href,
      );
    }

    await page.reload();
    await expect(page.getByText("Shift complete", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".clinical-report").getByText("1/1", { exact: true })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("starts an untimed PTB clinical case, commits a decision, and returns grounded feedback", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=qtc_prolongation");

    await expect(page.getByRole("heading", { name: /Use the ECG to make the next decision/ })).toBeVisible();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start learning set" }).click();
    const started = await (await startResponse).json() as {
      session: { sessionId: string };
      next: { itemId: string; item: { ecg_ref: string } };
    };
    expect(isOpaqueEcgCapability(started.next.item.ecg_ref)).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), started.next.item.ecg_ref)).toBe(false);

    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Learn — untimed", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Conversational ECG tutor" })).toHaveCount(0);

    const precommitTutor = await page.request.post("/api/backend/tutor/message", {
      data: {
        mode: "practice",
        caseId: started.next.item.ecg_ref,
        message: "Tell me the answer before I commit.",
        clinicalContext: {
          contextId: "ct_not_committed_yet",
          sessionId: started.session.sessionId,
          itemId: started.next.itemId,
          answerId: 1,
          version: "clinical-post-feedback-v1",
        },
      },
    });
    expect(precommitTutor.status()).toBe(409);
    expect((await precommitTutor.json()).detail.code).toBe("clinical_tutor_context_not_ready");

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();

    const options = page.locator(".clinical-options").getByRole("button");
    await expect(options.first()).toBeVisible();
    await options.first().click();
    const answerResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(path);
    });
    await page.getByRole("button", { name: "Commit decision" }).click();
    const answerBody = await (await answerResponse).json() as {
      grade: { feedback: string };
      tutorContext: {
        contextId: string;
        sessionId: string;
        itemId: string;
        answerId: number;
        version: string;
      };
    };

    await expect(page.getByRole("heading", { name: /Good decision|Reconsider/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Next case|Finish learning set/ })).toBeVisible();
    await expect(page.locator(".clinical-clock")).toHaveAttribute("data-clock-phase", "feedback");
    await expect(page.locator(".clinical-clock")).toContainText("Decision submitted");

    const tutorRequest = page.waitForRequest((request) => request.url().endsWith("/api/backend/tutor/message"));
    const tutorResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/tutor/message"));
    await page.getByRole("button", { name: "Open tutor" }).first().click();
    await page.getByLabel("Message the tutor").fill("Why was my decision graded this way?");
    await page.getByRole("button", { name: "Send" }).click();
    const groundedRequest = (await tutorRequest).postDataJSON() as Record<string, unknown> & {
      clinicalContext: typeof answerBody.tutorContext;
      viewerState: Record<string, unknown>;
      lessonId: string;
    };
    expect(groundedRequest.caseId === started.next.item.ecg_ref).toBe(true);
    expect(groundedRequest.clinicalContext).toEqual(answerBody.tutorContext);
    expect(groundedRequest.lessonId).toBe(answerBody.tutorContext.contextId);
    expect(groundedRequest.viewerState).toEqual({ activity: "clinical_case_debrief", committed: true });
    expect(groundedRequest.viewerState).not.toHaveProperty("score");
    expect(groundedRequest.viewerState).not.toHaveProperty("correctObjectives");
    expect(groundedRequest.viewerState).not.toHaveProperty("missedObjectives");
    expect(groundedRequest.viewerState).not.toHaveProperty("prompt");
    const tutorHttpResponse = await tutorResponse;
    expect(tutorHttpResponse.status()).toBe(200);
    const tutorBody = await tutorHttpResponse.json() as {
      threadId: string;
      tutorMessage: string;
      schemaError?: string | null;
    };
    expect(tutorBody.threadId).toBeTruthy();
    expect(tutorBody.tutorMessage.trim().length).toBeGreaterThan(0);
    expect(tutorBody.schemaError ?? null).toBeNull();
    await expect(page.locator(".chat-bubble.tutor").last()).toContainText(
      tutorBody.tutorMessage,
      { timeout: 30_000 },
    );

    const threadResponse = await page.request.get(`/api/backend/tutor/thread/${tutorBody.threadId}`);
    expect(threadResponse.status()).toBe(200);
    const threadBody = await threadResponse.json() as {
      messages: Array<{ role: string; meta?: { clinicalContextId?: string | null } }>;
    };
    const persistedTutorTurn = threadBody.messages.at(-1);
    expect(persistedTutorTurn?.role).toBe("tutor");
    expect(persistedTutorTurn?.meta?.clinicalContextId).toBe(answerBody.tutorContext.contextId);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("ED Shift serves acute context and gives a fresh decision clock after first look", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice");
    await page.getByRole("button", { name: "Emergency dept" }).click();
    await page.getByRole("button", { name: "Shift (timed)" }).click();

    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start shift" }).click();
    const start = await (await startResponse).json() as { next: { clock: { orientSec: number; decideSec: number } } };
    const clock = page.locator(".clinical-clock");
    await expect(clock).toHaveAttribute("data-clock-phase", "orient", { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toHaveCount(0);

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();

    await expect(clock).toHaveAttribute("data-clock-phase", "decide");
    const remaining = Number.parseInt((await clock.locator("span").last().textContent()) ?? "0", 10);
    expect(remaining).toBeGreaterThanOrEqual(start.next.clock.decideSec - 5);
    expect(remaining).toBeLessThanOrEqual(start.next.clock.decideSec);
    const stem = ((await page.locator(".clinical-stem").textContent()) ?? "").toLowerCase();
    expect(stem).not.toMatch(/pre-?operative|routine clearance|medication-review visit|clinic visit|outpatient/);

    const submit = page.getByRole("button", { name: "Commit decision", exact: true });
    await expect(submit).toBeDisabled();
    await expect(page.locator(".clinical-stepwise, .clinical-options, .clinical-fill-in").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toHaveCount(0);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("timed decision clock decrements in epoch time and auto-submits at expiry", async ({ page }) => {
    test.setTimeout(90_000);
    const errors = collectConsoleErrors(page);
    // Clinical deadlines are absolute server timestamps, so this test waits for
    // the real authoritative deadline instead of forging expiry in the browser.
    await page.goto("/practice");
    await page.getByRole("button", { name: "Emergency dept" }).click();
    await page.getByRole("button", { name: "Shift (timed)" }).click();

    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start shift" }).click();
    const start = await (await startResponse).json() as { next: { clock: { decideSec: number } } };

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();

    const clock = page.locator(".clinical-clock");
    await expect(clock).toHaveAttribute("data-clock-phase", "decide");
    const seconds = async () => Number.parseInt((await clock.locator("span").last().textContent()) ?? "0", 10);
    const before = await seconds();
    await page.waitForTimeout(1_200);
    const after = await seconds();
    expect(after).toBeLessThan(before);
    expect(after).toBeGreaterThan(0);

    const automaticAnswer = page.waitForRequest((request) => {
      const path = new URL(request.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(path);
    }, { timeout: (start.next.clock.decideSec + 5) * 1_000 });
    const request = await automaticAnswer;
    expect(request.postDataJSON()).toMatchObject({ answer: {} });
    await expect(page.locator(".clinical-clock")).toHaveAttribute("data-clock-phase", "feedback", { timeout: 15_000 });

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("guided handoff records only formative clinical application without reviewed governance", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const conflicts: string[] = [];
    page.on("response", (response) => {
      if (response.status() === 409) conflicts.push(`${response.request().method()} ${new URL(response.url()).pathname}`);
    });
    await page.goto("/practice?focus=atrial_fibrillation&subskill=apply_in_context&support=independent&returnTo=/learn/tachyarrhythmias?scene=m06-s5");
    await expect(page.locator(".selection-note").filter({ hasText: "From your lesson" })).toContainText(/use in context/i);
    await page.getByRole("button", { name: "Emergency dept" }).click();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "Start learning set" }).click();

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();

    const options = page.locator(".clinical-options").getByRole("button");
    await expect(options.first()).toBeVisible({ timeout: 30_000 });
    await options.first().click();
    const receiptResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(path);
    });
    await page.getByRole("button", { name: "Commit decision" }).click();
    const response = await receiptResponse;
    expect(response.ok()).toBeTruthy();
    const body = await response.json() as {
      grade: {
        competencyReceipts: Array<{
          concept: string;
          subskill: string;
          evidenceLevel: string;
          formativeOnly: boolean;
          retentionEligible: boolean;
        }>;
      };
    };
    const receipt = body.grade.competencyReceipts.find((candidate) => (
      candidate.concept === "atrial_fibrillation" && candidate.subskill === "apply_in_context"
    ));
    expect(receipt).toMatchObject({
      evidenceLevel: "guided",
      formativeOnly: true,
      retentionEligible: false,
    });
    await expect(page.getByText(/Practice saved: Atrial fibrillation · use in context/i)).toBeVisible();
    expect(conflicts, `Unexpected conflict responses:\n${conflicts.join("\n")}`).toEqual([]);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("runs a harness-checked PTB stepwise case through the first-look boundary", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=av_block_third_degree");
    await page.getByRole("button", { name: "Ward" }).click();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "Start learning set" }).click();

    await expect(page.getByText("Real de-identified ECG · authored vignette", { exact: true })).toBeVisible();
    await expect(page.getByText("Patient context authored for learning", { exact: true })).toBeVisible();
    await expect(page.getByText("Ventricular rate?", { exact: true })).toHaveCount(0);
    await page.getByLabel("Dominant finding").selectOption("conduction_or_interval");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();

    await expect(page.getByRole("group", { name: /Ventricular rate/ })).toBeVisible();
    const stepGroups = page.locator(".clinical-stepwise fieldset");
    await expect(stepGroups).toHaveCount(1);
    await expect(page.getByText("P-wave to QRS relationship?", { exact: true })).toHaveCount(0);
    const firstStepChoice = stepGroups.nth(0).getByRole("button").first();
    await firstStepChoice.click();
    await expect(stepGroups).toHaveCount(1);
    await expect(page.getByText("P-wave to QRS relationship?", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Commit step and reveal next" }).click();
    await expect(firstStepChoice).toBeDisabled();
    await expect(stepGroups).toHaveCount(2);
    await expect(page.getByRole("group", { name: /P-wave to QRS relationship/ })).toBeVisible();
    await expect(page.locator(".clinical-options")).toHaveCount(0);
    await stepGroups.nth(1).getByRole("button").first().click();
    await page.getByRole("button", { name: "Commit step and reveal clinical choices" }).click();
    await expect(stepGroups.nth(1).getByRole("button").first()).toBeDisabled();
    await expect(page.getByText(/ECG sequence committed and locked/)).toBeVisible();
    await page.locator(".clinical-options").getByRole("button").first().click();
    let finalSubmissions = 0;
    page.on("request", (request) => {
      if (/\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(new URL(request.url()).pathname)) finalSubmissions += 1;
    });
    await page.getByRole("button", { name: "Commit decision", exact: true }).click();

    await expect(page.getByText(/Mixed ECG checks update mastery separately/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /Good decision/ })).toBeVisible();
    const firstLookFeedback = page.getByRole("region", { name: "Your first look, before the vignette" });
    await expect(firstLookFeedback).toContainText("Conduction or interval abnormality");
    await expect(firstLookFeedback).toContainText("Medium");
    await expect(firstLookFeedback).toContainText(/does not establish exact pathology recognition/i);
    expect(finalSubmissions).toBe(1);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("grades a key-safe timed PTB QT fill-in and preserves the mobile decision rail", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/");
    const startedResponse = await page.request.post("/api/backend/clinical/shift/start", {
      data: {
        lane: "clinic",
        tier: "shift",
        length: 1,
        focus: "qtc_prolongation",
        subskill: "measure",
      },
    });
    expect(startedResponse.ok()).toBeTruthy();
    const started = await startedResponse.json() as {
      session: { sessionId: string };
      next: { itemId: string; item: { ecg_ref: string; question_type: string; fill_in_task?: unknown } };
    };
    expect(started.next.item.question_type).toBe("fillin");
    expect(isOpaqueEcgCapability(started.next.item.ecg_ref)).toBe(true);
    expect(started.next.item).not.toHaveProperty("fill_in_task");

    await page.goto("/practice");
    await expect(page.getByText("Measure from the ECG", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("Dominant finding").selectOption("conduction_or_interval");
    await page.getByRole("button", { name: "Medium" }).click();
    const revealResponse = page.waitForResponse((response) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/context$/.test(new URL(response.url()).pathname)
    ));
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();
    const revealed = await (await revealResponse).json() as {
      item: { fill_in_task: Record<string, unknown> };
    };
    expect(revealed.item.fill_in_task).toEqual({
      response_label: "Estimated QT interval",
      unit: "ms",
      min_value: 200,
      max_value: 800,
      step: 10,
    });
    expect(revealed.item.fill_in_task).not.toHaveProperty("expected_feature");
    expect(revealed.item.fill_in_task).not.toHaveProperty("tolerance");

    const measurement = page.getByLabel("Estimated QT interval (ms)");
    await expect(measurement).toBeVisible();
    await measurement.fill("500");
    await expect(page.locator(".clinical-clock")).toHaveAttribute("data-clock-phase", "decide");
    await expect(page.getByRole("button", { name: "Commit decision", exact: true })).toBeDisabled();
    await page.locator(".clinical-confidence").getByRole("button", { name: "Medium" }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(measurement).toBeVisible();
    const measurementBox = await measurement.boundingBox();
    expect(measurementBox).not.toBeNull();
    expect(measurementBox!.x + measurementBox!.width).toBeLessThanOrEqual(390);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    const answerRequest = page.waitForRequest((request) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(new URL(request.url()).pathname)
    ));
    const answerResponse = page.waitForResponse((response) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(new URL(response.url()).pathname)
    ));
    await page.getByRole("button", { name: "Commit decision", exact: true }).click();
    expect((await answerRequest).postDataJSON()).toMatchObject({ answer: { fillInValue: 500 } });
    const graded = await (await answerResponse).json() as {
      grade: {
        score: number;
        axisScores: Record<string, number>;
        competencyReceipts: Array<{ concept: string; subskill: string; formativeOnly: boolean }>;
      };
    };
    expect(graded.grade.score).toBe(1);
    expect(graded.grade.axisScores.measurement_accuracy).toBe(1);
    expect(graded.grade.competencyReceipts).toContainEqual(expect.objectContaining({
      concept: "qtc_prolongation",
      subskill: "measure",
      formativeOnly: true,
    }));
    await expect(page.getByRole("heading", { name: /Good decision/ })).toBeVisible();
    await expect(page.getByText(/Practice saved.*Prolonged QTc.*measure/i)).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("matches ECG, vignette, and unsupported evidence with keyboard-native controls", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/");
    const startedResponse = await page.request.post("/api/backend/clinical/shift/start", {
      data: {
        lane: "clinic",
        tier: "shift",
        length: 1,
        focus: "left_ventricular_hypertrophy",
      },
    });
    expect(startedResponse.ok()).toBeTruthy();
    const started = await startedResponse.json() as {
      next: { item: { question_type: string; matching_task?: unknown } };
    };
    expect(started.next.item.question_type).toBe("matching");
    expect(started.next.item).not.toHaveProperty("matching_task");

    await page.goto("/practice");
    await expect(page.getByText("Match evidence to meaning", { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("Dominant finding").selectOption("chamber_or_voltage");
    await page.getByRole("group", { name: "First-look confidence" })
      .getByRole("button", { name: "High", exact: true })
      .click();
    const revealResponse = page.waitForResponse((response) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/context$/.test(new URL(response.url()).pathname)
    ));
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();
    const revealed = await (await revealResponse).json() as {
      item: {
        matching_task: {
          choices: Array<{ id: string; label: string }>;
          rows: Array<{ id: string; clause: string }>;
        };
      };
    };
    const publicTask = revealed.item.matching_task;
    expect(publicTask.choices).toHaveLength(3);
    expect(publicTask.rows).toHaveLength(3);
    for (const row of publicTask.rows) {
      expect(Object.keys(row).sort()).toEqual(["clause", "id"]);
    }
    const serializedTask = JSON.stringify(publicTask);
    for (const hidden of ["source_type", "correct_choice_id", "source_reference", "objective_id"]) {
      expect(serializedTask).not.toContain(hidden);
    }

    const submit = page.getByRole("button", { name: "Commit decision", exact: true });
    const selects = page.locator(".clinical-matching-row select");
    await expect(selects).toHaveCount(3);
    await expect(submit).toBeDisabled();
    const matches: Record<string, string> = {};
    for (let index = 0; index < publicTask.rows.length; index += 1) {
      const row = publicTask.rows[index];
      const target = row.clause.startsWith("Encounter setting:")
        ? { id: "context", key: "p" }
        : row.clause.startsWith("Claim:")
          ? { id: "unsupported", key: "n" }
          : { id: "ecg", key: "s" };
      const select = selects.nth(index);
      await select.focus();
      await page.keyboard.press(target.key);
      await expect(select).toHaveValue(target.id);
      matches[row.id] = target.id;
    }
    await expect(submit).toBeDisabled();
    const confidence = page.locator(".clinical-confidence").getByRole("button", { name: "Medium" });
    await confidence.focus();
    await page.keyboard.press("Space");
    await expect(confidence).toHaveAttribute("aria-pressed", "true");
    await expect(submit).toBeEnabled();

    const answerRequest = page.waitForRequest((request) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(new URL(request.url()).pathname)
    ));
    const answerResponse = page.waitForResponse((response) => (
      /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(new URL(response.url()).pathname)
    ));
    await submit.click();
    expect((await answerRequest).postDataJSON()).toMatchObject({
      answer: { matches, confidence: 3 },
    });
    const graded = await (await answerResponse).json() as {
      grade: {
        score: number;
        matchingCorrect: boolean;
        matchingResults: Array<{ correct: boolean; correctChoiceId: string }>;
        competencyReceipts: unknown[];
      };
    };
    expect(graded.grade.score).toBe(1);
    expect(graded.grade.matchingCorrect).toBe(true);
    expect(graded.grade.matchingResults.every((result) => result.correct)).toBe(true);
    expect(graded.grade.competencyReceipts).toEqual([]);
    await expect(page.getByRole("heading", { name: /Evidence sorted/ })).toBeVisible();
    const review = page.getByRole("region", { name: "Evidence boundary review" });
    await expect(review).toContainText("Supported by this ECG packet");
    await expect(review).toContainText("Provided only by the authored vignette");
    await expect(review).toContainText("Not established by this ECG or vignette");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keyboard point entry populates and submits a Clinical click answer", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const liveGradeRequests: string[] = [];
    page.on("request", (request) => {
      if (/\/api\/backend\/grade\/(?:click|region)\//.test(new URL(request.url()).pathname)) {
        liveGradeRequests.push(request.url());
      }
    });
    await page.goto("/practice?focus=right_bundle_branch_block");
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start learning set" }).click();
    const started = await (await startResponse).json() as { session: { sessionId: string }; next: { item: { ecg_ref: string } } };
    expect(isOpaqueEcgCapability(started.next.item.ecg_ref)).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), started.next.item.ecg_ref)).toBe(false);
    const qrs = await strongestWaveformPoint(
      page,
      started.next.item.ecg_ref,
      "V1",
      5,
      7.5,
      { mode: "clinical", sessionId: started.session.sessionId },
    );

    await page.getByLabel("Dominant finding").selectOption("conduction_or_interval");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.getByLabel("Keyboard task lead").selectOption("V1");
    await page.getByLabel("Time cursor (seconds)").fill(qrs.timeSec.toFixed(3));
    await page.getByRole("button", { name: "Grade selected point" }).click();

    await expect(page.getByText(/Selected V1 at/)).toBeVisible();
    await expect(page.getByText(/Point recorded.*Correctness will be revealed after you commit/i)).toBeVisible();
    expect(liveGradeRequests).toEqual([]);
    const answerRequest = page.waitForRequest((request) => {
      const path = new URL(request.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(path);
    });
    const submit = page.getByRole("button", { name: "Commit decision", exact: true });
    await expect(submit).toBeEnabled();
    await submit.click();
    const submitted = (await answerRequest).postDataJSON() as { answer: { click: { lead: string; timeSec: number } } };
    expect(submitted.answer.click.lead).toBe("V1");
    expect(submitted.answer.click.timeSec).toBeGreaterThanOrEqual(0);
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider/ })).toBeVisible();
    await expect(page.locator(".clinical-axis-progress").first()).toBeVisible();
    await expect(page.locator(".clinical-axis .mastery-bar i")).toHaveCount(0);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("unsupported guided target fails closed instead of contaminating a receipt", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=ectopy&subskill=apply_in_context&returnTo=/learn/rhythm-ectopy?scene=M03.S14");

    await expect(page.locator(".warning").filter({ hasText: "No eligible formative Clinical case in Clinic currently checks ectopy" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Start learning set" })).toBeDisabled();
    await expect(page.getByRole("link", { name: "Return to lesson" })).toHaveAttribute("href", "/learn/rhythm-ectopy?scene=M03.S14");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("guided handoff availability is derived from the live Clinical bank", async ({ page }) => {
    await page.goto("/practice?focus=supraventricular_tachycardia&subskill=apply_in_context&lane=ed");
    const handoffNote = page.locator(".selection-note").filter({ hasText: "From your selected focus" });
    await expect(handoffNote).toContainText(/supraventricular tachycardia/i);
    await expect(handoffNote).toContainText("The first case focuses on");
    await expect(page.locator(".warning").filter({ hasText: "No eligible formative Clinical case" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Emergency dept" })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    const start = page.getByRole("button", { name: "Start learning set" });
    await expect(start).toBeEnabled();
    await start.click();
    await expect(page.getByText("Real de-identified ECG · authored vignette", { exact: true })).toBeVisible();
  });

  test("keeps the ECG first and the progressive case usable at 320px", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/practice?length=5");
    await expect(page.getByRole("button", { name: "Learn (untimed)" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "5 cases" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /Critical care/ })).toHaveCount(0);
    await expect(page.getByText(/Critical-care practice will open only after validated acute-rhythm ECGs/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    await page.getByRole("button", { name: "Start learning set" }).click();

    const waveform = page.getByRole("region", { name: "Clinical ECG waveform" });
    const firstLook = page.getByRole("complementary", { name: "Clinical first look" });
    await expect(waveform).toBeVisible({ timeout: 30_000 });
    await expect(firstLook).toBeVisible();
    await expect(page.locator(".clinical-stem, .clinical-options")).toHaveCount(0);
    const [waveformBox, firstLookBox] = await Promise.all([
      waveform.boundingBox(),
      firstLook.boundingBox(),
    ]);
    expect(waveformBox).not.toBeNull();
    expect(firstLookBox).not.toBeNull();
    expect(waveformBox!.y).toBeLessThan(firstLookBox!.y);
    expect(waveformBox!.x + waveformBox!.width).toBeLessThanOrEqual(320);
    expect(firstLookBox!.x + firstLookBox!.width).toBeLessThanOrEqual(320);
    await expect(firstLook).toHaveCSS("position", "static");
    await expect(firstLook).toHaveCSS("overflow-y", "visible");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);

    const shortTargets = await firstLook.locator("button:visible, select:visible").evaluateAll((controls) => (
      controls
        .map((control) => ({
          label: control.getAttribute("aria-label") || control.textContent || control.tagName,
          height: control.getBoundingClientRect().height,
        }))
        .filter((control) => control.height < 43.5)
    ));
    expect(shortTargets).toEqual([]);
    const accessibility = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(accessibility.violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.map((node) => node.target),
    }))).toEqual([]);

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look and reveal context/ }).click();
    const decision = page.getByRole("complementary", { name: "Clinical context and decision" });
    await expect(decision).toBeVisible();
    await expect(page.getByRole("region", { name: "Clinical context and decision prompt" })).toBeVisible();
    const decisionBox = await decision.boundingBox();
    expect(decisionBox).not.toBeNull();
    expect(decisionBox!.x + decisionBox!.width).toBeLessThanOrEqual(320);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
