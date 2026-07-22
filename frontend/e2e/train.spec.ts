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
    classification?: {
      version: string;
      kind: "single_choice";
      prompt: string;
      presentLabel: string;
      absentLabel: string;
      options: Array<{ id: "present" | "absent"; label: string }>;
      required: true;
    };
    task?: null | ({
      kind: "single_choice";
      prompt: string;
      options: Array<{ id: string; label: string }>;
      frameworkVersion?: string;
      frameworkSteps?: Array<{
        key: "rate" | "rhythm" | "axis" | "intervals" | "conduction" | "st_t" | "hypertrophy" | "synthesis";
        label: string;
        prompt: string;
        placeholder: string;
        choices?: string[];
      }>;
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
        systematicInterpretationComplete?: boolean;
        systematicInterpretation?: Record<string, string>;
        reviewedFramework?: Array<{
          key: string;
          label: string;
          review: string;
          grounded: boolean;
        }>;
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

test.describe("Focused Practice · durable campaigns", () => {
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

    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    await expect(recovery).toHaveCount(0);
    expect(activeChecks).toBeGreaterThanOrEqual(2);
  });

  test("finds a specific competency without scanning the full catalog", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train");

    const search = page.getByRole("searchbox", { name: "Find a topic" });
    await expect(search).toHaveAttribute("placeholder", "Search ECG topics", { timeout: 30_000 });
    await search.fill("bundle");
    const matches = page.locator('[aria-label="Available focused practice topics"]');
    await expect(matches.getByRole("button")).toHaveCount(3);
    await expect(matches).toContainText("Conduction");
    await matches.getByRole("button", { name: /^Right bundle branch block/ }).click();

    await expect(search).toHaveValue("");
    await expect(page.locator('[aria-label="Available focused practice topics"]').getByRole("button", { name: /^Right bundle branch block/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("heading", { name: "Right bundle branch block" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keeps the Focused Practice setup touch-sized at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/train");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    const controls = [
      page.getByRole("searchbox", { name: "Find a topic" }),
      page.getByRole("button", { name: "All topics" }),
      page.locator('[aria-label="Available focused practice topics"]').getByRole("button").first(),
      page.getByRole("group", { name: "Which skill do you want to practice?" }).getByRole("button").first(),
      page.getByRole("group", { name: "How long should this set be?" }).getByRole("button", { name: "Up to 5 ECGs" }),
      page.getByRole("button", { name: "Start focused practice" }),
    ];
    for (const control of controls) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("recommended Focused Practice length seeds setup but an explicit learner choice owns launch", async ({ page }) => {
    await page.goto("/train?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=discriminate&suggestedLength=25&returnTo=%2Fhome%3Fpanel%3Dplan");
    const lengths = page.getByRole("group", { name: "How long should this set be?" });
    await expect(lengths.getByRole("button", { name: "Up to 20 ECGs" })).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
    await lengths.getByRole("button", { name: "Up to 10 ECGs" }).click();
    await expect(page.getByRole("link", { name: "Return to study plan" })).toHaveAttribute("href", "/home?panel=plan");

    const start = page.getByRole("button", { name: "Start focused practice" });
    await expect(start).toBeEnabled({ timeout: 30_000 });
    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/training/campaigns"
      && request.method() === "POST"
    ));
    await start.click();
    expect((await startRequest).postDataJSON()).toMatchObject({ length: 10 });
  });

  test("preserves the raw QT measurement receipt while launching the reviewed QTc ECG family", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const availabilityResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/availability")
        && url.searchParams.get("conceptId") === "qtc_prolongation";
    });
    await page.goto("/train?concept=qtc_prolongation&receiptConcept=qt_interval&subskill=measure&returnTo=%2Flearn%2Frepolarization-safety");
    const availabilityHttp = await availabilityResponse;
    const availabilityText = await availabilityHttp.text();
    expect(availabilityHttp.ok(), availabilityText).toBeTruthy();
    const availability = JSON.parse(availabilityText) as {
      subskills: Record<string, { available: boolean }>;
    };
    expect(availability.subskills.measure.available).toBe(true);

    await expect(page.getByRole("heading", { name: "QTc prolongation" })).toBeVisible({ timeout: 30_000 });
    const skillChoices = page.getByRole("group", { name: "Which skill do you want to practice?" });
    await expect(skillChoices.getByRole("button", { name: /^Measure accurately/ })).toHaveAttribute("aria-pressed", "true");
    await expect(skillChoices.getByRole("button", { name: /^Recognize and name/ })).toHaveAttribute("aria-pressed", "false");
    const handoffNotice = page.locator(".train-setup-handoff");
    await expect(handoffNotice).toContainText(/chosen from your last activity for QT interval · Measure accurately/i);
    await expect(handoffNotice).toContainText(/closest available ECG topic is Prolonged QTc/i);

    const startRequest = page.waitForRequest((request) => (
      new URL(request.url()).pathname === "/api/backend/training/campaigns"
      && request.method() === "POST"
    ));
    const startResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname === "/api/backend/training/campaigns"
      && response.request().method() === "POST"
    ));
    const start = page.getByRole("button", { name: "Start focused practice" });
    await expect(start).toBeEnabled({ timeout: 30_000 });
    await start.click();

    const startBody = (await startRequest).postDataJSON() as {
      conceptId: string;
      subskill: string;
      contextKey: string;
    };
    expect(startBody.conceptId).toBe("qtc_prolongation");
    expect(startBody.subskill).toBe("measure");
    const context = new URLSearchParams(startBody.contextKey);
    expect(context.get("receiptConcept")).toBe("qt_interval");
    expect(context.get("returnTo")).toBe("/learn/repolarization-safety");
    expect(context.get("adaptive")).toBe("false");

    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.current?.task?.kind).toBe("numeric_fill_in");
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText(/QT interval · Measure accurately/i, { timeout: 30_000 });
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("saved session length prefills untouched Focused Practice setup while an explicit launch wins", async ({ page }) => {
    const saved = await page.request.put("/api/backend/learning/preferences", {
      data: { defaultSessionLength: 50 },
    });
    expect(saved.ok()).toBe(true);

    await page.goto("/train");
    const lengths = page.getByRole("group", { name: "How long should this set be?" });
    await expect(lengths.getByRole("button", { name: "Up to 20 ECGs" })).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });

    await page.goto("/train?suggestedLength=5");
    await expect(page.getByRole("group", { name: "How long should this set be?" }).getByRole("button", { name: "Up to 5 ECGs" })).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
  });

  test("keeps learner-facing lengths concise and disables unsupported topic-skill plans", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const availabilityResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/availability")
        && url.searchParams.get("conceptId") === "right_bundle_branch_block";
    });
    await page.goto("/train?concept=right_bundle_branch_block");
    const availability = await (await availabilityResponse).json() as {
      source: string;
      subskills: Record<string, { available: boolean }>;
    };

    await expect(page.getByRole("heading", { name: "What do you want to strengthen?" })).toBeVisible({ timeout: 30_000 });
    const lengths = page.getByRole("group", { name: "How long should this set be?" });
    await expect(lengths.getByRole("button", { name: "Up to 5 ECGs" })).toBeVisible();
    await expect(lengths.getByRole("button", { name: "Up to 10 ECGs" })).toBeVisible();
    await expect(lengths.getByRole("button", { name: "Up to 20 ECGs" })).toBeVisible();
    expect(availability.source).toBe("exact_target_index");
    expect(availability.subskills.recognize.available).toBe(true);
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);

    const search = page.getByRole("searchbox", { name: "Find a topic" });
    await search.fill("sinus rhythm");
    const unavailableAvailabilityResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/availability")
        && url.searchParams.get("conceptId") === "sinus_rhythm";
    });
    await page.locator('[aria-label="Available focused practice topics"]').getByRole("button", { name: /^Sinus rhythm/ }).click();
    const unavailableAvailability = await (await unavailableAvailabilityResponse).json() as {
      subskills: Record<string, { available: boolean }>;
    };
    expect(unavailableAvailability.subskills.measure.available).toBe(false);
    const measureSkill = page.getByRole("group", { name: "Which skill do you want to practice?" }).getByRole("button", { name: /^Measure accurately/ });
    await expect(measureSkill).toBeDisabled({ timeout: 30_000 });
    await expect(measureSkill).toContainText("Not available for this topic");
    await expect(measureSkill).toHaveAttribute("aria-pressed", "false");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("persists, resumes, grades exactly once, advances without a repeat, and keeps submitted ECGs reviewable after abandonment", async ({ page }) => {
    test.setTimeout(180_000);
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start focused practice" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.campaign).not.toBeNull();
    expect(started.campaign!.requestedLength).toBe(10);
    expect(started.campaign!.length).toBeLessThanOrEqual(started.campaign!.poolCount);
    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    expect(["ptbxl", "prepared_bundle", "leipzig-heart-center"]).toContain(started.current?.packet.source);
    expect(started.current?.packet).not.toHaveProperty("supported_objectives");
    expect(started.current?.packet).not.toHaveProperty("concept_confidence");
    expect(started.current?.slot).not.toHaveProperty("phase");
    expect(started.current?.slot).not.toHaveProperty("caseFocus");
    expect(started.current?.slot).not.toHaveProperty("targetPresent");
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

    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("ECG 1", { timeout: 30_000 });
    await expect(page.getByText(/Luna unlocks after you check the answer/i)).toBeVisible();
    await expect(page.locator('[data-learning-workspace="true"]')).toHaveAttribute("data-phase", "response");
    await expect(page.getByRole("button", { name: "Ask Luna" })).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(/Build target|Close mimic|Normal \/ negative|Unannounced transfer/);

    const targetDecision = page.getByRole("group", { name: "Target decision" });
    const draftedDecision = targetDecision.getByRole("button").first();
    await draftedDecision.click();
    const evidenceDraft = page.getByRole("textbox", { name: /What evidence drove your answer/i });
    await evidenceDraft.fill("Wide terminal R wave morphology in V1 with a broad lateral S wave.");

    const activeResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns/active"));
    await page.reload();
    const resumed = await (await activeResponse).json() as CampaignPayload;
    expect(resumed.current?.case.caseId === firstCaseId).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), firstCaseId)).toBe(false);
    await expect(targetDecision.getByRole("button").first()).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
    await expect(evidenceDraft).toHaveValue("Wide terminal R wave morphology in V1 with a broad lateral S wave.");
    await page.getByText("How this focused set works", { exact: true }).click();
    await expect(page.getByText(/Examples, close look-alikes, and normal contrasts are mixed/i)).toBeVisible();

    const tutorRestoreRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/backend/tutor/threads") && url.searchParams.get("caseId") === firstCaseId;
    });
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Check answer" }).click();
    const submitted = await (await submitResponse).json() as CampaignPayload;
    const tutorRestoreUrl = new URL((await tutorRestoreRequest).url());
    expect(tutorRestoreUrl.searchParams.get("scopeKey")).toBe(`training:${started.campaign!.campaignId}`);
    expect(submitted.answer?.grade.masteryDelta).toEqual({});
    expect(submitted.answer?.grade.legacyObjectiveMasterySuppressed).toBe(true);
    expect(submitted.replay).toBe(false);
    await expect(page.getByText("What the ECG supports", { exact: true })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('[data-learning-workspace="true"]')).toHaveAttribute("data-phase", "feedback");
    const tutorTrigger = page.getByRole("button", { name: "Ask Luna" });
    const tutorDialog = page.getByRole("dialog", { name: "Ask Luna about this ECG" });
    const tutorLayer = page.locator(".learning-tutor-layer");
    await expect(tutorTrigger).toHaveAttribute("aria-expanded", "false");
    await expect(tutorDialog).toBeHidden();
    expect(await tutorLayer.boundingBox()).toBeNull();
    await tutorTrigger.click();
    await expect(tutorTrigger).toHaveAttribute("aria-expanded", "true");
    await expect(tutorDialog).toBeVisible();
    await expect(tutorDialog).toContainText("Luna · ECG review");
    await expect(page.getByLabel("Message the tutor")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(tutorDialog).toBeHidden();
    await expect(tutorTrigger).toBeFocused();

    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: "Next ECG" }).click();
    const advanced = await (await nextResponse).json() as CampaignPayload;
    expect(advanced.current?.case.caseId !== firstCaseId).toBe(true);
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("ECG 2");

    const leaveSet = page.getByRole("button", { name: "Exit set" });
    await leaveSet.click();
    const confirmation = page.getByRole("alertdialog", { name: "Leave this training set?" });
    await expect(confirmation).toBeVisible();
    await expect(confirmation.getByRole("button", { name: "Keep training" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(confirmation).toHaveCount(0);
    await expect(leaveSet).toBeFocused();
    await leaveSet.click();
    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "What do you want to strengthen?" })).toBeVisible();

    await page.goto("/home?panel=activity");
    const history = page.locator("#home-panel-activity").getByTestId("session-history");
    const partialSet = history.locator("article").filter({ hasText: "Partial Focused set" });
    await expect(partialSet).toContainText(/1 of \d+ submitted · ended early/, { timeout: 30_000 });
    await partialSet.getByRole("link", { name: /Review Partial Focused set from/ }).click();
    await expect(page.getByRole("heading", { name: "Partial Focused set" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Submitted ECGs" })).toBeVisible();
    await page.getByText("Submitted ECG 1", { exact: true }).click();
    await page.getByRole("link", { name: "Review question & ECG" }).click();
    await expect(page.getByText(/Focused practice · Submitted/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "ECG replay" })).toBeVisible();
    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("opens the set review with ECG review, Luna feedback, progress, and scheduling handoffs", async ({ page }) => {
    test.setTimeout(120_000);
    const startResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns")
      && response.request().method() === "POST"
    ));
    await page.goto("/train?concept=right_bundle_branch_block&suggestedLength=5");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start focused practice" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.campaign?.length).toBe(5);

    for (let position = 0; position < 5; position += 1) {
      await expect(page.getByRole("region", { name: "Focused training set" })).toContainText(`ECG ${position + 1}`, { timeout: 30_000 });
      await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
      const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
      await page.getByRole("button", { name: "Check answer" }).click();
      expect((await submitResponse).ok()).toBeTruthy();
      await expect(page.getByText("What the ECG supports", { exact: true })).toBeVisible({ timeout: 30_000 });
      if (position < 4) {
        const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
        await page.getByRole("button", { name: "Next ECG" }).click();
        expect((await nextResponse).ok()).toBeTruthy();
      }
    }

    const reviewEntry = page.getByRole("button", { name: "Review this set" });
    await expect(reviewEntry).toBeVisible({ timeout: 60_000 });
    await reviewEntry.click();

    await expect(page.getByRole("heading", { name: "Turn this set into your next read." })).toBeVisible();
    await expect(page.getByRole("region", { name: "Focused practice results" })).toContainText("Pattern decisions");
    await expect(page.getByRole("heading", { name: "See the exact questions and traces again" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Feedback grounded in this set" })).toBeVisible();
    await expect(page.getByText("Situation", { exact: true })).toBeVisible();
    await expect(page.getByText("What you did", { exact: true })).toBeVisible();
    await expect(page.getByText("Impact", { exact: true })).toBeVisible();
    await expect(page.getByText("Next step", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /Schedule a revisit/ })).toHaveAttribute("href", "/home?panel=calendar");
    await expect(page.getByRole("link", { name: /View progress/ })).toHaveAttribute("href", "/home?panel=competencies");
    await expect(page.getByRole("link", { name: /Use it in a clinical case/ })).toHaveAttribute(
      "href",
      "/practice?focus=right_bundle_branch_block&subskill=apply_in_context&lane=clinic&length=5",
    );
    await expect(page.getByRole("link", { name: /Open learning history/ })).toHaveAttribute("href", "/home?panel=activity");

    await page.route("**/api/backend/training/campaigns", async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "A fresh focused set is temporarily unavailable." }),
      });
    });
    await page.getByRole("button", { name: "Start another set" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The training set could not be started. Try again." })).toBeVisible();
  });

  test("shows confidence in Focused review only when calibration was the practiced skill", async ({ page }) => {
    const session = (sessionRef: string, subskill: "recognize" | "calibrate_confidence") => ({
      sessionRef,
      mode: "training",
      status: "complete",
      attempted: 1,
      total: 1,
      score: 0.8,
      correctCount: null,
      flaggedCount: 0,
      focusCompetencies: [{ objectiveId: "right_bundle_branch_block", subskill, mappingSource: "session_focus" }],
      startedAt: "2026-07-18T14:00:00Z",
      completedAt: "2026-07-18T14:05:00Z",
      reviewAvailable: true,
    });
    const review = (sessionRef: string, subskill: "recognize" | "calibrate_confidence", confidence: number) => ({
      version: "learning-session-review-v1",
      session: session(sessionRef, subskill),
      attempts: [{
        index: 1,
        score: 0.8,
        competencies: [{
          objectiveId: "right_bundle_branch_block",
          subskill,
          score: 0.8,
          mappingSource: "committed_event",
        }],
        confidence,
        assistance: { hintsUsed: 0 },
        flagged: false,
      }],
    });

    await page.route("**/api/backend/learning/sessions/focused-recognize-review", (route) => route.fulfill({
      json: review("focused-recognize-review", "recognize", 5),
    }));
    await page.route("**/api/backend/learning/sessions/focused-calibration-review", (route) => route.fulfill({
      json: review("focused-calibration-review", "calibrate_confidence", 2),
    }));

    await page.goto("/home/review/focused-recognize-review");
    await expect(page.getByRole("heading", { name: "Focused practice" })).toBeVisible();
    await expect(page.getByText("Lower-confidence answers", { exact: true })).toHaveCount(0);
    await page.getByText("Question 1", { exact: true }).click();
    await expect(page.getByText(/Confidence (?:5\/5|not recorded)/)).toHaveCount(0);

    await page.goto("/home/review/focused-calibration-review");
    await expect(page.getByRole("heading", { name: "Focused practice" })).toBeVisible();
    const confidenceCard = page.getByLabel("Session summary").locator("article").filter({ hasText: "Lower-confidence answers" });
    await expect(confidenceCard.getByText("1 of 1", { exact: true })).toBeVisible();
    await page.getByText("Question 1", { exact: true }).click();
    await expect(page.getByText(/Confidence 2\/5/)).toBeVisible();
  });

  test("never carries the previous case waveform across a failed next-case load", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start focused practice" }).click();
    const viewer = page.getByRole("region", { name: "Training ECG waveform" });
    await expect(viewer.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.getByText("What the ECG supports", { exact: true })).toBeVisible({ timeout: 60_000 });

    await page.route("**/api/backend/training/campaigns/*/waveform/*?*", async (route) => {
      await route.abort("failed");
    });
    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: "Next ECG" }).click();
    const nextPayload = await (await nextResponse).json() as CampaignPayload;
    const nextEcgRef = nextPayload.current!.case.caseId;
    expect(isOpaqueEcgCapability(nextEcgRef)).toBe(true);
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("ECG 2");
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
    await page.getByRole("button", { name: "Exit set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
  });

  test("keeps the active ECG dominant with a scrolling response rail across desktop and mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start focused practice" }).click();

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

    await page.getByRole("button", { name: "Exit set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    await expect(page.getByRole("region", { name: "Configure focused practice" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("focused WCT campaigns include all 130 expert targets and launch a blinded eligible waveform", async ({ page }) => {
    test.skip(
      process.env.E2E_CORPUS_PROFILE === "compact-clinical",
      "Requires the audited full release corpus and Leipzig rhythm windows; the checked CI fixture contains only the 103 real PTB Clinical ECGs.",
    );
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    const poolResponse = await page.request.get(
      "/api/backend/training/campaigns/pool?conceptId=wide_complex_tachycardia&subskill=recognize",
    );
    expect(poolResponse.ok()).toBe(true);
    const pool = await poolResponse.json() as TrainingPoolPayload;
    await page.goto("/train?concept=wide_complex_tachycardia&subskill=recognize");

    expect(pool.source).toBe("audited_waveform_only");
    expect(pool.conceptId).toBe("wide_complex_tachycardia");
    expect(pool.subskill).toBe("recognize");
    expect(pool.roleCounts.target).toBe(130);
    expect(pool.eligibleDistinct).toBeGreaterThanOrEqual(5_000);
    expect(pool.roleCounts.target + pool.roleCounts.mimic + pool.roleCounts.negative).toBe(pool.eligibleDistinct);
    await expect(page.getByRole("heading", { name: /Wide.complex tachycardia/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(
      `${pool.roleCounts.target.toLocaleString()} pattern present · ${pool.roleCounts.mimic.toLocaleString()} close comparisons · ${pool.roleCounts.negative.toLocaleString()} other contrasts`,
    )).toHaveCount(0);

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled();
    await page.getByRole("button", { name: "Start focused practice" }).click();
    const started = await (await startResponse).json() as CampaignPayload;

    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    expect(["leipzig-heart-center", "ptbxl", "prepared_bundle"]).toContain(started.current?.packet.source);
    expect(started.current?.slot).not.toHaveProperty("phase");
    expect(started.current?.slot).not.toHaveProperty("caseFocus");
    expect(started.current?.slot).not.toHaveProperty("targetPresent");
    expect(isOpaqueEcgCapability(started.current?.case.caseId)).toBe(true);
    expect(await page.locator("body").evaluate((body, ecgRef) => body.innerHTML.includes(ecgRef), started.current!.case.caseId)).toBe(false);
    await expect(page.locator("body")).not.toContainText("Leipzig expert rhythm window");
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("ECG 1");

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Exit set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "What do you want to strengthen?" })).toBeVisible();
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
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start focused practice" }).click();
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

    await expect(page.getByRole("complementary", { name: "Training response" })).toContainText(/measure accurately/i, { timeout: 30_000 });
    const toolbar = page.getByRole("toolbar", { name: "ECG tools" });
    await expect(toolbar.getByLabel("Active tool: Measure")).toBeVisible();
    await expect(toolbar.getByRole("button", { name: "Undo last ECG task mark" })).toBeDisabled();
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.locator(".viewer-keyboard-fields select").selectOption(qrs.lead);
    await page.getByLabel("First boundary (seconds)").fill(qrsStart.toFixed(3));
    await page.getByLabel("Second boundary (seconds)").fill(qrsEnd.toFixed(3));
    await page.getByRole("button", { name: "Use these caliper boundaries" }).click();
    await expect(page.getByText(/span recorded at 100 ms.*Correctness will be revealed after you check your answer/i)).toBeVisible();
    await expect(toolbar.getByRole("button", { name: "Undo last ECG task mark" })).toBeEnabled();
    expect(liveGradeRequests).toEqual([]);
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const numericTask = started.current!.task!;
    expect(numericTask.kind).toBe("numeric_fill_in");
    if (numericTask.kind !== "numeric_fill_in") throw new Error("Expected a numeric fill-in task");
    const valueInput = page.getByLabel(`${numericTask.responseLabel} (${numericTask.unit})`);
    await valueInput.focus();
    await page.keyboard.type("100");
    await expect(valueInput).toHaveValue("100");
    const checkAnswer = page.getByRole("button", { name: "Check answer" });
    await expect(checkAnswer).toBeEnabled();

    const activeResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns/active"));
    await page.reload();
    const resumed = await (await activeResponse).json() as CampaignPayload;
    expect(resumed.current?.case.caseId).toBe(caseId);
    await expect(page.locator('[data-evidence-mode="caliper"]')).toHaveCount(1, { timeout: 30_000 });
    await expect(toolbar.getByRole("button", { name: "Undo last ECG task mark" })).toBeEnabled();
    await expect(page.getByRole("group", { name: "Target decision" }).getByRole("button").first()).toHaveAttribute("aria-pressed", "true");
    await expect(valueInput).toHaveValue("100");
    await expect(checkAnswer).toBeEnabled();

    await toolbar.getByRole("button", { name: "Clear ECG task marks" }).click();
    await expect(page.locator('[data-evidence-mode="caliper"]')).toHaveCount(0);
    await expect(toolbar.getByRole("button", { name: "Undo last ECG task mark" })).toBeDisabled();
    await expect(toolbar.getByRole("button", { name: "Clear ECG task marks" })).toBeDisabled();
    await expect(checkAnswer).toBeDisabled();

    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.locator(".viewer-keyboard-fields select").selectOption(qrs.lead);
    await page.getByLabel("First boundary (seconds)").fill(qrsStart.toFixed(3));
    await page.getByLabel("Second boundary (seconds)").fill(qrsEnd.toFixed(3));
    await page.getByRole("button", { name: "Use these caliper boundaries" }).click();
    await expect(page.locator('[data-evidence-mode="caliper"]')).toHaveCount(1);
    await expect(checkAnswer).toBeEnabled();

    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await checkAnswer.click();
    const submitHttp = await submitResponse;
    const submitText = await submitHttp.text();
    expect(submitHttp.ok(), submitText).toBeTruthy();
    const submitted = JSON.parse(submitText) as CampaignPayload;
    const result = submitted.answer?.grade.trainingSubskillTaskResult;
    expect(result?.kind).toBe("numeric_fill_in");
    expect(result?.complete).toBe(true);
    expect(typeof result?.expectedValue).toBe("number");
    expect(typeof result?.tolerance).toBe("number");
    await expect(page.getByRole("region", { name: "Measurement answer review" })).toContainText(/reviewed ECG measurement/i);
    await expect(page.locator('[data-evidence-mode="caliper"]')).toHaveCount(1);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("grounded clinical matching is keyboard-first, key-safe before checking, and exact after checking", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=apply_in_context");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start focused practice" }).click();

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.locator(".train-subskill-options").getByRole("radio").first().click();
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.getByText("What the ECG supports", { exact: true })).toBeVisible({ timeout: 60_000 });

    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: "Next ECG" }).click();
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
    const matchGroups = page.getByRole("group", { name: /Evidence source for statement/ });
    await expect(matchGroups).toHaveCount(3);
    for (let index = 0; index < task.rows.length; index += 1) {
      const clause = task.rows[index].clause;
      const expectedLabel = clause.startsWith("First verify")
        ? "ECG finding to integrate"
        : clause.startsWith("Then obtain")
          ? "Context required before a pathway"
          : "Bounded clinical application";
      const expectedChoice = task.choices.find((choice) => choice.label === expectedLabel);
      expect(expectedChoice, `Missing semantic source for ${clause}`).toBeDefined();
      const choice = matchGroups.nth(index).getByRole("button", { name: expectedLabel, exact: true });
      await choice.focus();
      await page.keyboard.press("Enter");
      await expect(choice).toHaveAttribute("aria-pressed", "true");
    }
    const commit = page.getByRole("button", { name: "Check answer" });
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
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns")
      && response.request().method() === "POST"
    ));
    await page.getByRole("button", { name: "Start focused practice" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    await expect(page.getByRole("complementary", { name: "Training response" })).toContainText(/explain the mechanism/i, { timeout: 30_000 });
    const mechanism = page.getByRole("radiogroup", { name: /Which causal chain best explains/i });
    await expect(mechanism).toBeVisible();
    await expect(mechanism.getByRole("radio")).toHaveCount(4);
    await expect(page.getByText(/connects the morphology to its electrophysiology/i)).toBeVisible();
    await expect(page.getByText(/A hint helps you find the evidence/i)).toBeVisible();
    await expect(page.getByText("Ready when you complete:", { exact: true })).toBeVisible();
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
    await page.getByRole("button", { name: "Check answer" }).click();
    const submitHttp = await submitResponse;
    const submitText = await submitHttp.text();
    expect(submitHttp.ok(), submitText).toBeTruthy();
    const submitted = JSON.parse(submitText) as CampaignPayload;
    const currentAnswer = (submitted.current as unknown as { answer?: CampaignPayload["answer"] } | null)?.answer;
    const submittedAnswer = submitted.answer ?? currentAnswer;
    const skillResult = submittedAnswer?.grade.trainingSubskillTaskResult;
    expect(skillResult?.kind).toBe("single_choice");
    expect(skillResult?.correctAnswer).toBeTruthy();
    const patternAxis = page.locator(".train-feedback-axes > div").filter({ hasText: "Target-pattern decision" });
    await expect(patternAxis).toHaveCount(1);
    await expect(patternAxis).toContainText(submittedAnswer?.summary.classificationCorrect ? "Correct" : "Needs review");
    await expect(page.getByRole("region", { name: "Selected skill answer review" })).toContainText("Correct response:");
    expect(["ptbxl", "prepared_bundle", "leipzig-heart-center"]).toContain(started.current?.packet.source);
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
    await expect(page.getByRole("heading", { name: "What do you want to strengthen?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("group", { name: "Which skill do you want to practice?" }).getByRole("button", { name: /^Measure accurately/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("status")).toContainText(/Starting this plan will close your saved set/i);
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

  test("complete-interpretation practice saves one uncluttered step at a time and submits all eight domains", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const campaignId = "focused-systematic-e2e";
    const ecgRef = `ec_${"S".repeat(43)}`;
    const now = "2026-07-18T14:00:00Z";
    const classification = {
      version: "focused-classification-v1",
      kind: "single_choice" as const,
      prompt: "Does this tracing support right bundle branch block?",
      presentLabel: "RBBB supported",
      absentLabel: "RBBB not supported",
      options: [
        { id: "present" as const, label: "RBBB supported" },
        { id: "absent" as const, label: "RBBB not supported" },
      ],
      required: true as const,
    };
    const frameworkSteps = [
      { key: "rate", label: "Rate", prompt: "Estimate atrial and ventricular rates.", placeholder: "Rate and rate band" },
      { key: "rhythm", label: "Rhythm", prompt: "Describe regularity, atrial activity, and AV relationship.", placeholder: "Rhythm and AV relationship" },
      { key: "axis", label: "Axis", prompt: "Classify the frontal QRS axis.", placeholder: "Axis and supporting polarity" },
      { key: "intervals", label: "P waves & intervals", prompt: "Assess P waves, PR, and the major intervals.", placeholder: "P waves, PR, and intervals" },
      { key: "conduction", label: "QRS & conduction", prompt: "Describe QRS width, morphology, and conduction.", placeholder: "QRS and conduction" },
      { key: "st_t", label: "ST-T & QT", prompt: "Review ST segments, T waves, and QT/QTc.", placeholder: "Repolarization findings" },
      { key: "hypertrophy", label: "Chambers & progression", prompt: "Check chamber patterns and R-wave progression.", placeholder: "Chambers and progression" },
      { key: "synthesis", label: "Final impression", prompt: "Prioritize the important ECG findings.", placeholder: "Evidence-bounded final impression" },
    ] as const;
    const synthesisPrompt = "Which reviewed synthesis stays within the ECG evidence?";
    const synthesisOptions = [
      { id: "choice_reviewed", label: "Prioritize the conduction finding and its decisive morphology without inferring acuity." },
      { id: "choice_overreach", label: "Diagnose the clinical cause and choose treatment from this resting ECG alone." },
    ];
    const entries = {
      rate: "Ventricular rate approximately 72 bpm",
      rhythm: "Regular sinus rhythm with 1:1 AV conduction",
      axis: "Normal frontal axis; QRS positive in I and aVF",
      intervals: "Sinus P waves with normal PR and QTc intervals",
      conduction: "QRS 132 ms with terminal right-precordial forces",
      st_t: "Secondary anterior repolarization change without acute ST elevation",
      hypertrophy: "No supported chamber hypertrophy; R-wave progression reviewed",
      synthesis: "Sinus rhythm with right bundle branch block morphology; no unsupported clinical inference.",
    };
    const task = {
      kind: "single_choice" as const,
      subskill: "synthesize",
      variant: 0,
      prompt: synthesisPrompt,
      options: synthesisOptions,
      frameworkVersion: "focused-systematic-interpretation-v1",
      frameworkSteps,
      required: true,
      gradingBoundary: "Completion and the reviewed synthesis choice are checked deterministically.",
    };
    const pendingSummary = {
      attempted: 0,
      correct: 0,
      classificationCorrect: 0,
      fullTaskCorrect: 0,
      independentReceipts: 0,
      byPhase: {},
      recent: [],
    };
    const pendingPayload = {
      campaign: {
        campaignId,
        learnerId: "e2e-focused-learner",
        conceptId: "right_bundle_branch_block",
        subskill: "synthesize",
        requestedLength: 5,
        length: 5,
        poolCount: 5,
        position: 0,
        pendingCaseId: ecgRef,
        feedbackCaseId: null,
        status: "active",
        contextKey: "",
        createdAt: now,
        updatedAt: now,
        abandonedAt: null,
      },
      current: {
        kind: "pending",
        slot: {
          position: 0,
          caseId: ecgRef,
          status: "pending",
          servedAt: now,
          answeredAt: null,
        },
        case: {
          caseId: ecgRef,
          displayId: "Focused ECG 1",
          source: "ptbxl",
          teachingTier: "A",
          clinicalStem: "12-lead ECG obtained for interval evaluation.",
          topConcepts: [],
          report: "",
          studentFacing: true,
        },
        packet: {
          case_id: ecgRef,
          display_id: "Focused ECG 1",
          clinical_stem: "12-lead ECG obtained for interval evaluation.",
          source: "ptbxl",
          blinded: true,
          waveform: {
            sampling_frequency: 100,
            duration_sec: 10,
            leads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"],
            source: "ptbxl",
          },
          ptbxl_plus: {
            features: {},
            fiducials: { rois: [] },
            median_beats: { available: false, samplingFrequency: 100, durationMs: 0, leads: [], beats: {} },
            measurements: {},
          },
          signal_quality: { status: "ok", reasons: [] },
          teaching_tier: "A",
          inclusion_reasons: [],
          exclusion_reasons: [],
        },
        classification,
        task,
      },
      summary: pendingSummary,
      replay: false,
    } as unknown as CampaignPayload;
    let campaignStarted = false;
    let submitted = false;
    let submitBody: Record<string, unknown> | null = null;

    await page.route("**/api/backend/tutor/threads?*", (route) => route.fulfill({ json: { threads: [] } }));
    await page.route("**/api/backend/training/campaigns**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      if (path.endsWith("/availability")) {
        await route.fulfill({ json: {
          conceptId: "right_bundle_branch_block",
          source: "exact_target_index",
          subskills: Object.fromEntries([
            "recognize", "localize", "measure", "discriminate", "explain_mechanism", "synthesize", "apply_in_context", "calibrate_confidence",
          ].map((subskill) => [subskill, { available: true, independentReceiptsAvailable: subskill !== "synthesize" }])),
        } });
        return;
      }
      if (path.endsWith("/active")) {
        await route.fulfill({ json: campaignStarted ? pendingPayload : { campaign: null, current: null, summary: null } });
        return;
      }
      if (path.includes(`/training/campaigns/${campaignId}/waveform/`)) {
        await route.fulfill({ json: {
          caseId: ecgRef,
          samplingFrequency: 100,
          durationSec: 10,
          startSec: 0,
          endSec: 10,
          leads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"].map((lead) => ({
            lead,
            points: [
              { timeSec: 0, amplitudeMv: 0 },
              { timeSec: 0.5, amplitudeMv: lead === "V1" ? 0.9 : 0.25 },
              { timeSec: 1, amplitudeMv: 0 },
            ],
          })),
        } });
        return;
      }
      if (path.endsWith(`/${campaignId}/submit`)) {
        submitBody = request.postDataJSON() as Record<string, unknown>;
        submitted = true;
        const reviewedFramework = frameworkSteps.map((step) => ({
          key: step.key,
          label: step.label,
          review: step.key === "rate"
            ? "Packet-grounded review: ventricular rate 72 bpm."
            : `Packet-grounded review: ${step.label} was checked against the reviewed ECG packet.`,
          grounded: true,
        }));
        const answer = {
          answerId: 1,
          campaignId,
          position: 0,
          caseId: ecgRef,
          response: {
            selectedAnswer: "present",
            confidence: null,
            hintsUsed: 0,
            evidenceNote: "",
            subskillTaskAnswer: "choice_reviewed",
            subskillTaskMatches: {},
            subskillTaskValue: null,
            structuredInterpretation: entries,
            expectedAnswer: "present",
          },
          grade: {
            masteryDelta: {},
            legacyObjectiveMasterySuppressed: true,
            trainingSubskillTaskResult: {
              kind: "single_choice",
              complete: true,
              correct: true,
              score: 1,
              submittedAnswer: "choice_reviewed",
              correctAnswer: "choice_reviewed",
              systematicInterpretationComplete: true,
              systematicInterpretation: entries,
              reviewedFramework,
            },
          },
          tutor: null,
          receipt: { requestedEvidenceLevel: "guided", effectiveEvidenceLevel: "guided", receipts: [] },
          summary: {
            position: 0,
            caseId: ecgRef,
            correct: true,
            classificationCorrect: true,
            focusGrounded: true,
            selectedResponse: "present",
            confidence: null,
            hintsUsed: 0,
            evidenceLevel: "guided",
            misconceptions: [],
          },
          attemptId: 1,
          createdAt: now,
        };
        await route.fulfill({ json: {
          ...pendingPayload,
          current: { ...pendingPayload.current, kind: "feedback", answer },
          answer,
          summary: { ...pendingSummary, attempted: 1, correct: 1, classificationCorrect: 1, fullTaskCorrect: 1 },
          replay: false,
        } });
        return;
      }
      if (path.endsWith("/training/campaigns") && request.method() === "POST") {
        campaignStarted = true;
        await route.fulfill({ json: pendingPayload });
        return;
      }
      await route.continue();
    });

    await page.goto("/train?concept=right_bundle_branch_block&subskill=synthesize");
    const skillGroup = page.getByRole("group", { name: "Which skill do you want to practice?" });
    await expect(skillGroup.getByRole("button", { name: /^Complete an interpretation/ })).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled();
    await page.getByRole("button", { name: "Start focused practice" }).click();

    await expect(page.getByRole("complementary", { name: "Training response" })).toContainText("Complete ECG interpretation");
    const visibleStepFields = page.locator('input[id^="focused-interpretation-"]:visible, textarea[id^="focused-interpretation-"]:visible');
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(visibleStepFields).toHaveCount(1);
    await expect(visibleStepFields.first()).toBeEditable();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await expect(page.getByText(frameworkSteps[0].prompt, { exact: true })).toBeVisible();
    await expect(page.getByText(frameworkSteps[1].prompt, { exact: true })).toHaveCount(0);
    await page.setViewportSize({ width: 1280, height: 900 });
    const continueButton = page.getByRole("button", { name: "Save & continue" });
    await expect(continueButton).toBeDisabled();

    for (const step of frameworkSteps.slice(0, 4)) {
      await expect(page.getByText("Current step", { exact: true }).locator("..").getByRole("heading", { name: step.label })).toBeVisible();
      await page.getByLabel("Add a more precise entry, or edit the quick choice").fill(entries[step.key]);
      await expect(continueButton).toBeEnabled();
      await continueButton.click();
    }
    await page.waitForFunction((key) => {
      const stored = Object.entries(window.sessionStorage).find(([name]) => name.includes(String(key)))?.[1];
      if (!stored) return false;
      const draft = JSON.parse(stored) as { interpretationStepIndex?: number; structuredInterpretation?: { rate?: string } };
      return draft.interpretationStepIndex === 4 && draft.structuredInterpretation?.rate === "Ventricular rate approximately 72 bpm";
    }, campaignId);

    await page.reload();
    await expect(page.getByText("Current step", { exact: true }).locator("..").getByRole("heading", { name: "QRS & conduction" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Overview" }).click();
    const overview = page.getByRole("list", { name: "Interpretation overview" });
    await expect(overview).toContainText(entries.rate);
    await expect(overview).toContainText(entries.intervals);
    await overview.getByRole("button", { name: /QRS & conduction/ }).click();

    for (const step of frameworkSteps.slice(4, 7)) {
      await expect(page.getByText("Current step", { exact: true }).locator("..").getByRole("heading", { name: step.label })).toBeVisible();
      await page.getByLabel("Add a more precise entry, or edit the quick choice").fill(entries[step.key]);
      await page.getByRole("button", { name: "Save & continue" }).click();
    }

    await expect(page.getByText("Current step", { exact: true }).locator("..").getByRole("heading", { name: "Final impression" })).toBeVisible();
    const reviewSteps = page.getByRole("button", { name: "Review steps" });
    const checkAnswer = page.getByRole("button", { name: "Check answer" });
    const impression = page.getByLabel("Your evidence-limited impression");
    await expect(reviewSteps).toBeDisabled();
    await impression.fill("RBBB");
    await expect(reviewSteps).toBeDisabled();
    await impression.fill(entries.synthesis);
    await expect(reviewSteps).toBeDisabled();
    await page.getByRole("group", { name: classification.prompt }).getByRole("button", { name: classification.presentLabel }).click();
    await expect(reviewSteps).toBeDisabled();
    await expect(checkAnswer).toBeDisabled();
    await page.getByRole("group", { name: synthesisPrompt }).getByRole("radio", { name: synthesisOptions[0].label }).click();
    await expect(reviewSteps).toBeEnabled();
    await expect(checkAnswer).toBeEnabled();
    await reviewSteps.click();
    await expect(page.getByRole("list", { name: "Interpretation overview" })).toContainText(entries.synthesis);

    const submitRequestPromise = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith(`/${campaignId}/submit`));
    await checkAnswer.click();
    await submitRequestPromise;
    expect(submitted).toBe(true);
    const capturedSubmitBody = submitBody as unknown as Record<string, unknown>;
    expect(capturedSubmitBody).toMatchObject({
      caseId: ecgRef,
      selectedAnswer: "present",
      subskillTaskAnswer: "choice_reviewed",
      structuredInterpretation: entries,
    });
    expect(Object.keys(capturedSubmitBody.structuredInterpretation as Record<string, string>).sort()).toEqual([
      "axis", "conduction", "hypertrophy", "intervals", "rate", "rhythm", "st_t", "synthesis",
    ]);
    const frameworkReview = page.getByRole("region", { name: "Compare each step with grounded ECG data" });
    await expect(frameworkReview).toBeVisible();
    await expect(frameworkReview).toContainText("Packet-grounded review: ventricular rate 72 bpm.");
    await expect(frameworkReview).toContainText(entries.synthesis);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("clinical-application practice requires a reviewed context choice, not prose length", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=apply_in_context");
    await expect(page.getByRole("button", { name: "Start focused practice" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start focused practice" }).click();
    await expect(page.getByRole("complementary", { name: "Training response" })).toContainText(/apply in clinical context/i, { timeout: 30_000 });
    await expect(page.getByText(/clinical information needed to use this ECG safely/i)).toBeVisible();
    await expect(page.getByText(/Management decisions are practiced in Clinical Cases/i)).toBeVisible();
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await page.getByRole("textbox", { name: /What evidence drove your answer/i }).fill("Another long free-text statement that must not count as a clinical decision rubric.");
    await expect(page.getByRole("button", { name: "Check answer" })).toBeDisabled();
    await page.getByRole("radiogroup", { name: /Which next-step statement/i }).getByRole("radio").first().click();
    await expect(page.getByRole("button", { name: "Check answer" })).toBeEnabled();

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
