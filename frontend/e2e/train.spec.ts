import { test, expect, type Page } from "@playwright/test";
import { collectConsoleErrors, isOpaqueEcgCapability, registerVerifiedE2ELearner, strongestWaveformPoint } from "./helpers";

type CampaignPayload = {
  campaign: null | {
    campaignId: string;
    requestedLength: number;
    length: number;
    poolCount: number;
    pendingCaseId: string | null;
    status: string;
  };
  current: null | {
    kind: "pending" | "feedback";
    case: { caseId: string; displayId: string };
    slot: { targetPresent?: boolean };
    task?: null | ({
      kind: "single_choice";
      prompt: string;
      options: Array<{ id: string; label: string }>;
    } | {
      kind: "matching";
      prompt: string;
      rows: Array<{ id: string; clause: string }>;
      choices: Array<{ id: string; label: string }>;
    } | {
      kind: "numeric_fill_in";
      prompt: string;
      responseLabel: string;
      unit: string;
      minValue: number;
      maxValue: number;
      step: number;
    } | {
      kind: "confidence_commit";
      prompt: string;
    });
    packet: {
      case_id: string;
      display_id: string;
      blinded: boolean;
      source: string;
      supported_objectives?: string[];
      concept_confidence?: Record<string, unknown>;
      ptbxl_plus: { fiducials: { rois: Array<{ lead: string; concept: string; timeStartSec: number; timeEndSec: number }> } };
    };
  };
  answer?: {
    summary: {
      classificationCorrect: boolean;
      correct: boolean;
    };
    grade: {
      masteryDelta: Record<string, number>;
      legacyObjectiveMasterySuppressed: boolean;
      trainingSubskillTaskResult?: {
        kind: "matching" | "numeric_fill_in" | "single_choice";
        complete: boolean;
        correct: boolean;
        submittedAnswer?: string | null;
        correctAnswer?: string | null;
        expectedValue?: number;
        tolerance?: number;
        rows?: Array<{
          rowId: string;
          correctChoiceId: string;
          submittedChoiceId: string | null;
          correct: boolean;
        }>;
      } | null;
    };
  };
  replay?: boolean;
};

type TrainingPoolPayload = {
  conceptId: string;
  subskill: string;
  eligibleDistinct: number;
  roleCounts: { target: number; mimic: number; negative: number };
  source: string;
};

async function abandonActiveCampaign(page: Page) {
  const active = await page.request.get("/api/backend/training/campaigns/active");
  if (!active.ok()) return;
  const payload = await active.json() as CampaignPayload;
  if (payload.campaign) {
    await page.request.post(`/api/backend/training/campaigns/${payload.campaign.campaignId}/abandon`);
  }
}

test.describe("Mode 2 · durable Training campaigns", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "train" });
    await abandonActiveCampaign(page);
  });

  test("announces a failed saved-set check and retries it without a page reload", async ({ page }) => {
    let activeChecks = 0;
    let allowRecovery = false;
    await page.route("**/api/backend/training/campaigns/active", async (route) => {
      activeChecks += 1;
      if (!allowRecovery) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporarily unavailable" }) });
        return;
      }
      await route.fulfill({ json: { campaign: null, current: null } });
    });

    await page.goto("/train");
    const retry = page.getByRole("button", { name: "Retry loading" });
    const recovery = page.getByRole("alert").filter({ has: retry });
    await expect(recovery).toBeVisible();
    allowRecovery = true;
    await retry.click();

    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await expect(recovery).toHaveCount(0);
    expect(activeChecks).toBeGreaterThanOrEqual(2);
  });

  test("finds a specific competency without scanning the full catalog", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train");

    const search = page.getByRole("searchbox", { name: "Find a concept" });
    await expect(search).toHaveAttribute("placeholder", "Search concepts", { timeout: 30_000 });
    await search.fill("bundle");
    const matches = page.locator(".train-concept-results");
    await expect(matches.getByRole("button")).toHaveCount(3);
    await expect(matches).toContainText("Conduction disturbance");
    await matches.getByRole("button", { name: /^Right bundle branch block/ }).click();

    await expect(page.getByLabel("Target concept")).toHaveValue("right_bundle_branch_block");
    await expect(search).toHaveValue("");
    await expect(matches).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keeps the Focused Practice setup touch-sized at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/train");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    const controls = [
      page.getByRole("searchbox", { name: "Find a concept" }),
      page.getByLabel("Target concept"),
      page.getByLabel("Skill to practice"),
      page.getByRole("button", { name: /Recommended|Use recommended skill/ }),
      page.getByLabel("Requested unique ECGs"),
      page.getByRole("button", { name: "Start training" }),
    ];
    for (const control of controls) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("recommended Training length seeds setup but an explicit learner choice owns launch", async ({ page }) => {
    await page.goto("/train?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=discriminate&suggestedLength=25&returnTo=%2Fprofile%3Ftab%3Dplan");
    const length = page.getByLabel("Requested unique ECGs");
    await expect(length).toHaveValue("25", { timeout: 30_000 });
    await length.selectOption("50");
    await expect(page.getByRole("link", { name: "Return to study plan" })).toHaveAttribute("href", "/profile?tab=plan");

    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/training/campaigns"
      && request.method() === "POST"
    ));
    await page.getByRole("button", { name: "Start training" }).click();
    expect((await startRequest).postDataJSON()).toMatchObject({ length: 50 });
  });

  test("saved session length prefills untouched Training setup while an explicit launch wins", async ({ page }) => {
    const saved = await page.request.put("/api/backend/learning/preferences", {
      data: { defaultSessionLength: 50 },
    });
    expect(saved.ok()).toBe(true);

    await page.goto("/train");
    const length = page.getByLabel("Requested unique ECGs");
    await expect(length).toHaveValue("50", { timeout: 30_000 });

    await page.goto("/train?suggestedLength=25");
    await expect(page.getByLabel("Requested unique ECGs")).toHaveValue("25", { timeout: 30_000 });
  });

  test("shows every supported scale target and an honest distinct-pool cap before starting", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const poolResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/pool")
        && url.searchParams.get("conceptId") === "right_bundle_branch_block";
    });
    await page.goto("/train?concept=right_bundle_branch_block");
    const pool = await (await poolResponse).json() as { eligibleDistinct: number; source: string };

    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".train-page-setup > .panel")).toHaveCount(1);
    await expect(page.getByLabel("Requested unique ECGs").locator("option")).toHaveText([
      "10", "25", "50", "100", "500", "1,000", "5,000",
    ]);
    await expect(page.getByText(`${pool.eligibleDistinct.toLocaleString()} unique ECGs available`)).toBeVisible();
    expect(pool.source).toBe("audited_waveform_only");
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);

    await page.getByLabel("Requested unique ECGs").selectOption("5000");
    if (pool.eligibleDistinct < 5000) {
      await expect(page.getByText(new RegExp(`capped at ${pool.eligibleDistinct.toLocaleString()}`, "i"))).toBeVisible();
      await expect(page.getByText(/no synthetic or repeated case will fill the gap/i)).toBeVisible();
    }

    await page.getByLabel("Target concept").selectOption("sinus_rhythm");
    await page.getByLabel("Skill to practice").selectOption("measure");
    const setup = page.getByRole("region", { name: "Configure training set" });
    await expect(setup.getByRole("status")).toContainText(/No distinct reviewed real ECGs currently support this concept and skill combination/i);
    await expect(setup.getByRole("status")).toContainText(/Choose another skill or finding to continue/i);
    await expect(page.getByRole("button", { name: "Start training" })).toBeDisabled();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("persists, resumes, grades exactly once, advances without a repeat, and abandons", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start training" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.campaign).not.toBeNull();
    expect(started.campaign!.requestedLength).toBe(10);
    expect(started.campaign!.length).toBeLessThanOrEqual(started.campaign!.poolCount);
    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    expect(["ptbxl", "prepared_bundle", "leipzig-heart-center"]).toContain(started.current?.packet.source);
    expect(started.current?.packet).not.toHaveProperty("supported_objectives");
    expect(started.current?.packet).not.toHaveProperty("concept_confidence");
    const firstCaseId = started.current!.case.caseId;
    expect(isOpaqueEcgCapability(firstCaseId)).toBe(true);
    expect(started.current!.packet.case_id === firstCaseId).toBe(true);
    expect(started.current!.case.displayId !== firstCaseId).toBe(true);
    expect(started.current!.packet.display_id !== firstCaseId).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), firstCaseId)).toBe(false);
    await expect.poll(() => page.evaluate(({ campaignId, ecgRef }) => (
      performance.getEntriesByType("resource").some((entry) => (
        entry.name.includes(`/api/backend/training/campaigns/${campaignId}/waveform/${encodeURIComponent(ecgRef)}`)
      ))
    ), { campaignId: started.campaign!.campaignId, ecgRef: firstCaseId })).toBe(true);

    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("Case 1", { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Tutor after commitment" })).toBeVisible();
    await expect(page.locator('[data-learning-workspace="true"]')).toHaveAttribute("data-phase", "response");
    await expect(page.getByRole("button", { name: "Open tutor" })).toHaveCount(0);

    const activeResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns/active"));
    await page.reload();
    const resumed = await (await activeResponse).json() as CampaignPayload;
    expect(resumed.current?.case.caseId === firstCaseId).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), firstCaseId)).toBe(false);
    await page.getByText("How this set is mixed", { exact: true }).click();
    await expect(page.getByText(/Resumed your saved training set/i)).toBeVisible({ timeout: 30_000 });

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const tutorRestoreRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/backend/tutor/threads") && url.searchParams.get("caseId") === firstCaseId;
    });
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Commit answer" }).click();
    const submitted = await (await submitResponse).json() as CampaignPayload;
    const tutorRestoreUrl = new URL((await tutorRestoreRequest).url());
    expect(tutorRestoreUrl.searchParams.get("scopeKey")).toBe(`training:${started.campaign!.campaignId}`);
    expect(submitted.answer?.grade.masteryDelta).toEqual({});
    expect(submitted.answer?.grade.legacyObjectiveMasterySuppressed).toBe(true);
    expect(submitted.replay).toBe(false);
    await expect(page.getByRole("heading", { name: "Why this answer" })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('[data-learning-workspace="true"]')).toHaveAttribute("data-phase", "feedback");
    const tutorTrigger = page.getByRole("button", { name: "Open tutor" });
    const tutorDialog = page.getByRole("dialog", { name: "ECG tutor" });
    const tutorLayer = page.locator(".learning-tutor-layer");
    await expect(tutorTrigger).toHaveAttribute("aria-expanded", "false");
    await expect(tutorDialog).toBeHidden();
    expect(await tutorLayer.boundingBox()).toBeNull();
    await tutorTrigger.click();
    await expect(tutorTrigger).toHaveAttribute("aria-expanded", "true");
    await expect(tutorDialog).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(tutorDialog).toBeHidden();
    await expect(tutorTrigger).toBeFocused();

    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: /Next case in set/ }).click();
    const advanced = await (await nextResponse).json() as CampaignPayload;
    expect(advanced.current?.case.caseId !== firstCaseId).toBe(true);
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("Case 2");

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    const leaveSet = page.getByRole("button", { name: "Leave training set" });
    await leaveSet.click();
    const confirmation = page.getByRole("alertdialog", { name: "Leave this training set?" });
    await expect(confirmation).toBeVisible();
    await expect(confirmation.getByRole("button", { name: "Keep training" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(confirmation).toHaveCount(0);
    await expect(leaveSet).toBeFocused();
    await leaveSet.click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("never carries the previous case waveform across a failed next-case load", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start training" }).click();
    const viewer = page.getByRole("region", { name: "Training ECG waveform" });
    await expect(viewer.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.getByRole("button", { name: "Commit answer" }).click();
    await expect(page.getByRole("heading", { name: "Why this answer" })).toBeVisible({ timeout: 60_000 });

    await page.route("**/api/backend/training/campaigns/*/waveform/*?*", async (route) => {
      await route.abort("failed");
    });
    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: /Next case in set/ }).click();
    const nextPayload = await (await nextResponse).json() as CampaignPayload;
    const nextEcgRef = nextPayload.current!.case.caseId;
    expect(isOpaqueEcgCapability(nextEcgRef)).toBe(true);
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("Case 2");
    await expect(viewer.getByRole("img", { name: /12-lead ECG/i })).toHaveCount(0);
    await expect(viewer.getByText("This ECG could not be loaded.")).toBeVisible();
    await expect(viewer.getByRole("button", { name: "Retry ECG" })).toBeVisible();
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), nextEcgRef)).toBe(false);

    await page.unroute("**/api/backend/training/campaigns/*/waveform/*?*");
    const retriedWaveform = page.waitForResponse((response) => (
      new URL(response.url()).pathname.includes(`/waveform/${encodeURIComponent(nextEcgRef)}`)
    ));
    await viewer.getByRole("button", { name: "Retry ECG" }).click();
    expect((await retriedWaveform).ok()).toBeTruthy();
    await expect(viewer.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Leave training set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
  });

  test("keeps the active ECG dominant with a scrolling response rail across desktop and mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start training" }).click();

    const shell = page.locator('[data-learning-workspace="true"]');
    const sessionBar = page.locator(".train-session-bar");
    const waveform = page.getByRole("region", { name: "Training ECG waveform" });
    const response = page.getByRole("complementary", { name: "Training response" });
    const disclosure = page.locator(".train-disclosure");
    await expect(shell).toBeVisible({ timeout: 30_000 });
    await expect(response).toHaveAttribute("data-response-phase", "response");

    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1280, height: 800 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
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
      expect(responseBox!.y + responseBox!.height).toBeLessThanOrEqual(viewport.height + 1);
      expect(disclosureBox!.height).toBeLessThanOrEqual(76);
      await expect(response).toHaveCSS("overflow-y", "auto");
      await expect(sessionBar).toHaveCSS("position", "sticky");
      const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(documentWidth).toBeLessThanOrEqual(viewport.width);
    }

    await page.setViewportSize({ width: 390, height: 844 });
    const mobileTaskDock = page.getByRole("region", { name: "Current training task" });
    await expect(mobileTaskDock).toBeVisible();
    await expect(mobileTaskDock).toContainText(/Classify|Does this tracing|After checking/i);
    const [mobileTask, mobileWaveform, mobileResponse] = await Promise.all([
      mobileTaskDock.boundingBox(),
      waveform.boundingBox(),
      response.boundingBox(),
    ]);
    expect(mobileTask).not.toBeNull();
    expect(mobileWaveform).not.toBeNull();
    expect(mobileResponse).not.toBeNull();
    expect(mobileTask!.y).toBeLessThan(mobileWaveform!.y);
    expect(mobileWaveform!.y).toBeLessThan(mobileResponse!.y);
    expect(mobileWaveform!.width).toBeLessThanOrEqual(358);
    expect(mobileResponse!.width).toBeLessThanOrEqual(358);
    await expect(response).toHaveCSS("position", "static");
    await expect(response).toHaveCSS("overflow-y", "visible");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    await page.getByRole("button", { name: "Leave training set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    await expect(page.getByRole("region", { name: "Configure training set" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("focused WCT campaigns expose all 130 expert targets and open on a Leipzig rhythm window", async ({ page }) => {
    test.skip(
      process.env.E2E_CORPUS_PROFILE === "compact-clinical",
      "Requires the audited full release corpus and Leipzig rhythm windows; the checked CI fixture contains only the 103 real PTB Clinical ECGs.",
    );
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    const poolResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/pool")
        && url.searchParams.get("conceptId") === "wide_complex_tachycardia"
        && url.searchParams.get("subskill") === "recognize";
    });
    await page.goto("/train?concept=wide_complex_tachycardia&subskill=recognize");
    const pool = await (await poolResponse).json() as TrainingPoolPayload;

    expect(pool.source).toBe("audited_waveform_only");
    expect(pool.conceptId).toBe("wide_complex_tachycardia");
    expect(pool.subskill).toBe("recognize");
    expect(pool.roleCounts.target).toBe(130);
    expect(pool.eligibleDistinct).toBeGreaterThanOrEqual(5_000);
    expect(pool.roleCounts.target + pool.roleCounts.mimic + pool.roleCounts.negative).toBe(pool.eligibleDistinct);
    await expect(page.getByText(
      `${pool.roleCounts.target.toLocaleString()} pattern present · ${pool.roleCounts.mimic.toLocaleString()} close comparisons · ${pool.roleCounts.negative.toLocaleString()} other contrasts`,
    )).toBeVisible({ timeout: 30_000 });

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start training" }).click();
    const started = await (await startResponse).json() as CampaignPayload;

    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    expect(started.current?.packet.source).toBe("leipzig-heart-center");
    expect(isOpaqueEcgCapability(started.current?.case.caseId)).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), started.current!.case.caseId)).toBe(false);
    const sourceRegion = page.getByRole("region", { name: "ECG source" });
    await expect(sourceRegion).toContainText("Reviewed real ECG", { timeout: 30_000 });
    await expect(sourceRegion).not.toContainText("Leipzig expert rhythm window");
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("Case 1");

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Leave training set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("measure campaigns retain the keyboard-accessible trace-native evidence gate", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const liveGradeRequests: string[] = [];
    page.on("request", (request) => {
      if (/\/api\/backend\/grade\/(?:click|region)\//.test(new URL(request.url()).pathname)) {
        liveGradeRequests.push(request.url());
      }
    });
    await page.goto("/train?concept=right_bundle_branch_block&subskill=measure");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start training" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.current?.packet.ptbxl_plus.fiducials.rois).toEqual([]);
    expect(started.current?.task?.kind).toBe("numeric_fill_in");
    expect(started.current?.task).not.toHaveProperty("expectedValue");
    expect(started.current?.task).not.toHaveProperty("tolerance");
    expect(started.current?.task).not.toHaveProperty("packetFeature");
    const caseId = started.current!.case.caseId;
    // V1 occupies the 5.0–7.5 s acquisition column in the standard 3×4 view.
    const qrs = await strongestWaveformPoint(
      page,
      caseId,
      "V1",
      5,
      7.5,
      { mode: "training", sessionId: started.campaign!.campaignId },
    );
    const qrsStart = Math.max(0, qrs.timeSec - 0.04);
    const qrsEnd = qrsStart + 0.1;

    await expect(page.getByRole("complementary", { name: "Training response" })).toContainText("Measure it", { timeout: 30_000 });
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.locator(".viewer-keyboard-fields select").selectOption(qrs.lead);
    await page.getByLabel("First boundary (seconds)").fill(qrsStart.toFixed(3));
    await page.getByLabel("Second boundary (seconds)").fill(qrsEnd.toFixed(3));
    await page.getByRole("button", { name: "Use these caliper boundaries" }).click();
    await expect(page.getByText(/span recorded at 100 ms.*Correctness will be revealed after commit/i)).toBeVisible();
    expect(liveGradeRequests).toEqual([]);
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const numericTask = started.current!.task!;
    expect(numericTask.kind).toBe("numeric_fill_in");
    if (numericTask.kind !== "numeric_fill_in") throw new Error("Expected a numeric fill-in task");
    const valueInput = page.getByLabel(`${numericTask.responseLabel} (${numericTask.unit})`);
    await valueInput.focus();
    await page.keyboard.type("100");
    await expect(valueInput).toHaveValue("100");
    await expect(page.getByRole("button", { name: "Commit answer" })).toBeEnabled();
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Commit answer" }).click();
    const submitted = await (await submitResponse).json() as CampaignPayload;
    const result = submitted.answer?.grade.trainingSubskillTaskResult;
    expect(result?.kind).toBe("numeric_fill_in");
    expect(result?.complete).toBe(true);
    expect(typeof result?.expectedValue).toBe("number");
    expect(typeof result?.tolerance).toBe("number");
    await expect(page.getByRole("region", { name: "Measurement answer review" })).toContainText(/exact packet measurement/i);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("grounded matching is keyboard-first, key-safe before commit, and exact after commit", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=synthesize");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start training" }).click();

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.locator(".train-subskill-options").getByRole("radio").first().click();
    await page.getByRole("button", { name: "Commit answer" }).click();
    await expect(page.getByRole("heading", { name: "Why this answer" })).toBeVisible({ timeout: 60_000 });

    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: /Next case in set/ }).click();
    const pending = await (await nextResponse).json() as CampaignPayload;
    const task = pending.current?.task;
    expect(task?.kind).toBe("matching");
    if (!task || task.kind !== "matching") throw new Error("Expected a grounded matching task");
    const publicTask = JSON.stringify(task).toLowerCase();
    expect(publicTask).not.toContain("right bundle branch block");
    expect(publicTask).not.toContain("left bundle branch block");
    expect(publicTask).not.toContain("correctchoiceid");
    expect(publicTask).not.toContain("supportedobjective");
    expect(publicTask).not.toContain("waveformlead");

    await expect(page.getByRole("group", { name: "Target decision" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const selects = page.locator(".train-subskill-matching select");
    await expect(selects).toHaveCount(3);
    for (let index = 0; index < task.rows.length; index += 1) {
      const clause = task.rows[index].clause;
      const expectedLabel = clause.startsWith("Recorded waveform:")
        ? "Waveform acquisition fact"
        : clause.startsWith("The packet's reviewed ECG finding label")
          ? "Audited label field"
          : "Not established by this ECG packet";
      const expectedChoice = task.choices.find((choice) => choice.label === expectedLabel);
      expect(expectedChoice, `Missing semantic source for ${clause}`).toBeDefined();
      const select = selects.nth(index);
      await select.focus();
      await page.keyboard.press(expectedLabel[0]);
      await expect(select).toHaveValue(expectedChoice!.id);
    }
    const commit = page.getByRole("button", { name: "Commit answer" });
    await expect(commit).toBeEnabled();
    const submitRequest = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith("/submit"));
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await commit.click();
    const requestBody = (await submitRequest).postDataJSON() as { subskillTaskMatches: Record<string, string> };
    expect(Object.keys(requestBody.subskillTaskMatches)).toHaveLength(3);
    expect(new Set(Object.values(requestBody.subskillTaskMatches)).size).toBe(3);
    const submitted = await (await submitResponse).json() as CampaignPayload;
    const result = submitted.answer?.grade.trainingSubskillTaskResult;
    expect(result?.kind).toBe("matching");
    expect(result?.complete).toBe(true);
    expect(result?.correct).toBe(true);
    expect(result?.rows).toHaveLength(3);
    await expect(page.getByText("Evidence source review", { exact: true })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".train-task-feedback li")).toHaveCount(3);
    await expect(page.locator(".train-task-feedback")).toContainText("Correct source:");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("mechanism handoff opens a reviewed server-graded choice task", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=explain_mechanism&returnTo=/review");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns")
      && response.request().method() === "POST"
    ));
    await page.getByRole("button", { name: "Start training" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    await expect(page.getByText("Practice explain mechanism")).toBeVisible({ timeout: 30_000 });
    const mechanism = page.getByRole("radiogroup", { name: /Which causal chain best explains/i });
    await expect(mechanism).toBeVisible();
    await expect(mechanism.getByRole("radio")).toHaveCount(4);
    await expect(page.getByText(/does not infer symptoms, acuity, cause, or treatment/i)).toBeVisible();
    await expect(page.getByText(/A visual hint changes this ECG to coached practice/i)).toBeVisible();
    await expect(page.getByText("Before you commit", { exact: true })).toBeVisible();
    await expect(page.getByText("Choose the target-pattern decision.", { exact: true })).toBeVisible();
    await expect(page.getByText("Answer the selected-skill question.", { exact: true })).toBeVisible();

    expect(started.current?.slot).not.toHaveProperty("targetPresent");
    const targetDecision = page.getByRole("group", { name: "Target decision" });
    const targetOptions = targetDecision.getByRole("button");
    expect(await targetOptions.count()).toBe(2);
    await targetOptions.nth(0).click();
    const mechanismOptions = mechanism.getByRole("radio");
    expect(await mechanismOptions.count()).toBe(4);
    await mechanismOptions.nth(0).click();
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Commit answer" }).click();
    const submitted = await (await submitResponse).json() as CampaignPayload;
    const skillResult = submitted.answer?.grade.trainingSubskillTaskResult;
    expect(skillResult?.kind).toBe("single_choice");
    expect(skillResult?.correctAnswer).toBeTruthy();
    const patternAxis = page.locator(".train-feedback-axes > div").filter({ hasText: "Target-pattern decision" });
    await expect(patternAxis).toHaveCount(1);
    await expect(patternAxis).toContainText(submitted.answer?.summary.classificationCorrect ? "Correct" : "Needs review");
    await expect(page.getByRole("region", { name: "Selected skill answer review" })).toContainText("Correct response:");
    await expect(page.getByRole("region", { name: "ECG source" })).toContainText(/PTB-XL|Leipzig/i);
    await expect(page.getByRole("link", { name: /Return/i })).toHaveAttribute("href", "/review");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("an explicit handoff replaces a conflicting saved set instead of silently resuming it", async ({ page }) => {
    const saved = await page.request.post("/api/backend/training/campaigns", {
      data: {
        conceptId: "right_bundle_branch_block",
        subskill: "recognize",
        length: 10,
        contextKey: "",
      },
    });
    expect(saved.ok()).toBeTruthy();

    await page.goto("/train?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=measure&returnTo=/rapid");
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Skill to practice")).toHaveValue("measure");
    await expect(page.getByRole("status")).toContainText(/targets a different competency than your saved set/i);
    const replaceButton = page.getByRole("button", { name: "Replace saved set and start" });
    await expect(replaceButton).toBeEnabled();

    const requestPromise = page.waitForRequest((request) => (
      new URL(request.url()).pathname.endsWith("/api/backend/training/campaigns")
      && request.method() === "POST"
    ));
    await replaceButton.click();
    const request = await requestPromise;
    expect(request.postDataJSON()).toMatchObject({
      conceptId: "right_bundle_branch_block",
      subskill: "measure",
      replaceActive: true,
    });
    await expect(page.getByRole("region", { name: "Focused training set" })).toBeVisible({ timeout: 30_000 });
  });

  test("synthesis and clinical-application Training require structured evidence, not prose length", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=synthesize");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start training" }).click();

    await expect(page.getByText("Practice synthesize")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/free-text length alone does not count/i)).toBeVisible();
    await expect(page.locator(".train-current-target .muted")).toHaveText(/Not assessed yet|Practiced · not independently checked|Current mastery estimate · \d+%/i);
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.getByLabel("Evidence note").fill("This deliberately long but meaningless note must not unlock semantic synthesis grading.");
    const commit = page.getByRole("button", { name: "Commit answer" });
    await expect(commit).toBeDisabled();
    await expect(page.getByText("Answer the selected-skill question.", { exact: true })).toBeVisible();
    await page.getByRole("radiogroup", { name: /Which one-line synthesis/i }).getByRole("radio").first().click();
    await expect(commit).toBeEnabled();

    await page.getByRole("button", { name: "Leave training set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    await page.goto("/train?concept=right_bundle_branch_block&subskill=apply_in_context");
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start training" }).click();
    await expect(page.getByText("Practice apply in context")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/context-boundary choice/i)).toBeVisible();
    await expect(page.getByText(/No patient vignette is present/i)).toBeVisible();
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.getByLabel("Evidence note").fill("Another long free-text statement that must not count as a clinical decision rubric.");
    await expect(page.getByRole("button", { name: "Commit answer" })).toBeDisabled();
    await page.getByRole("radiogroup", { name: /Which next-step statement/i }).getByRole("radio").first().click();
    await expect(page.getByRole("button", { name: "Commit answer" })).toBeEnabled();

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
