import { test, expect } from "@playwright/test";
import { collectConsoleErrors, randomUsername } from "./helpers";

test.describe("Mode 4 · Clinical Decisions", () => {
  test("refresh restores the owned pending item, context, feedback, and report", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/");
    const registered = await page.request.post("/api/backend/auth/register", {
      data: {
        username: randomUsername("clinical_resume"),
        password: "Sup3r-Secret-Pw!",
        displayName: "Clinical Resume Tester",
      },
    });
    expect(registered.ok()).toBeTruthy();
    const startedResponse = await page.request.post("/api/backend/clinical/shift/start", {
      data: { lane: "clinic", tier: "shift", length: 1, focus: "qtc_prolongation" },
    });
    expect(startedResponse.ok()).toBeTruthy();
    const started = await startedResponse.json() as { session: { sessionId: string }; next: { itemId: string } };

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

    await page.reload();
    await expect(page.getByText("Case 1 / 1", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".clinical-context-mask")).toBeVisible();
    const resumedOrient = await (await page.request.get("/api/backend/clinical/shift/active")).json() as { current: { clock: { orientDeadlineAt: string } } };
    expect(resumedOrient.current.clock.orientDeadlineAt).toBe(orientDeadline);
    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look & reveal clinical context/ }).click();
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
    await page.getByRole("button", { name: "Submit", exact: true }).click();
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toBeVisible({ timeout: 30_000 });

    await page.reload();
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Finish shift" })).toBeVisible();
    await page.getByRole("button", { name: "Finish shift" }).click();
    await expect(page.getByText("Shift complete", { exact: true })).toBeVisible();

    await page.reload();
    await expect(page.getByText("Shift complete", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("1/1", { exact: true })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("starts an untimed PTB clinical case, commits a decision, and returns grounded feedback", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=qtc_prolongation");

    await expect(page.getByRole("heading", { name: /Use the ECG to make the next decision/ })).toBeVisible();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "Start shift" }).click();

    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Learn — untimed", { exact: true })).toBeVisible();
    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look & reveal clinical context/ }).click();

    const options = page.locator(".clinical-options").getByRole("button");
    await expect(options.first()).toBeVisible();
    await options.first().click();
    await page.getByRole("button", { name: "Submit" }).click();

    await expect(page.getByRole("heading", { name: /Good decision|Reconsider/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Next case|Finish shift/ })).toBeVisible();
    await expect(page.locator(".clinical-clock")).toHaveAttribute("data-clock-phase", "feedback");
    await expect(page.locator(".clinical-clock")).toContainText("Decision submitted");

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("ED Shift serves acute context and gives a fresh decision clock after first look", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice");
    await page.getByRole("button", { name: "Emergency dept" }).click();

    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start shift" }).click();
    const start = await (await startResponse).json() as { next: { clock: { orientSec: number; decideSec: number } } };
    const clock = page.locator(".clinical-clock");
    await expect(clock).toHaveAttribute("data-clock-phase", "orient", { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toHaveCount(0);

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look & reveal clinical context/ }).click();

    await expect(clock).toHaveAttribute("data-clock-phase", "decide");
    const remaining = Number.parseInt((await clock.locator("span").last().textContent()) ?? "0", 10);
    expect(remaining).toBeGreaterThanOrEqual(start.next.clock.decideSec - 5);
    expect(remaining).toBeLessThanOrEqual(start.next.clock.decideSec);
    const stem = ((await page.locator(".clinical-stem").textContent()) ?? "").toLowerCase();
    expect(stem).not.toMatch(/pre-?operative|routine clearance|medication-review visit|clinic visit|outpatient/);

    const submit = page.getByRole("button", { name: "Submit", exact: true });
    await expect(submit).toBeDisabled();
    await expect(page.locator(".clinical-confidence")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider|Time/ })).toHaveCount(0);

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("guided handoff records only formative clinical application without reviewed governance", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=atrial_fibrillation&subskill=apply_in_context&support=independent&returnTo=/learn/tachyarrhythmias?scene=m06-s5");
    await expect(page.getByText(/through apply in context/i)).toBeVisible();
    await page.getByRole("button", { name: "Emergency dept" }).click();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "Start shift" }).click();

    await page.getByLabel("Dominant finding").selectOption("uncertain");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look & reveal clinical context/ }).click();

    const options = page.locator(".clinical-options").getByRole("button");
    await expect(options.first()).toBeVisible({ timeout: 30_000 });
    await options.first().click();
    const receiptResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(path);
    });
    await page.getByRole("button", { name: "Submit" }).click();
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
    await expect(page.getByText(/Server-graded formative apply in context (success|attempt) recorded for atrial fibrillation/i)).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("runs a harness-checked PTB stepwise case through the first-look boundary", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=av_block_third_degree");
    await page.getByRole("button", { name: "Ward" }).click();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    await page.getByRole("button", { name: "Start shift" }).click();

    await expect(page.getByText("Real de-identified ECG · authored vignette", { exact: true })).toBeVisible();
    await expect(page.getByText("Formative only", { exact: true })).toBeVisible();
    await expect(page.getByText("Ventricular rate?", { exact: true })).toHaveCount(0);
    await page.getByLabel("Dominant finding").selectOption("conduction_or_interval");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look & reveal clinical context/ }).click();

    await expect(page.getByRole("group", { name: /Ventricular rate/ })).toBeVisible();
    const stepGroups = page.locator(".clinical-stepwise fieldset");
    await stepGroups.nth(0).getByRole("button").first().click();
    await stepGroups.nth(1).getByRole("button").first().click();
    await page.locator(".clinical-options").getByRole("button").first().click();
    await page.getByRole("button", { name: "Submit", exact: true }).click();

    await expect(page.getByText(/Clinical application is formative practice only/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /Good decision/ })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("keyboard point entry populates and submits a Clinical click answer", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=right_bundle_branch_block");
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    const startResponse = page.waitForResponse((response) => response.url().endsWith("/api/backend/clinical/shift/start"));
    await page.getByRole("button", { name: "Start shift" }).click();
    const started = await (await startResponse).json() as { next: { item: { ecg_id: string } } };

    const packetResponse = await page.request.get(`/api/backend/cases/${started.next.item.ecg_id}/packet`);
    expect(packetResponse.ok()).toBeTruthy();
    const packet = await packetResponse.json() as {
      ptbxl_plus: { fiducials: { rois: Array<{ concept: string; lead: string; timeStartSec: number }> } };
    };
    const qrs = packet.ptbxl_plus.fiducials.rois.find((roi) => roi.concept === "qrs_complex" && roi.lead === "V1");
    expect(qrs).toBeTruthy();

    await page.getByLabel("Dominant finding").selectOption("conduction_or_interval");
    await page.getByRole("button", { name: "Medium" }).click();
    await page.getByRole("button", { name: /Commit first look & reveal clinical context/ }).click();
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.getByLabel("Keyboard task lead").selectOption("V1");
    await page.getByLabel("Time cursor (seconds)").fill(qrs!.timeStartSec.toFixed(3));
    await page.getByRole("button", { name: "Grade selected point" }).click();

    await expect(page.getByText(/Selected V1 at/)).toBeVisible();
    const answerRequest = page.waitForRequest((request) => {
      const path = new URL(request.url()).pathname;
      return /\/api\/backend\/clinical\/shift\/[^/]+\/answer$/.test(path);
    });
    const submit = page.getByRole("button", { name: "Submit", exact: true });
    await expect(submit).toBeEnabled();
    await submit.click();
    const submitted = (await answerRequest).postDataJSON() as { answer: { click: { lead: string; timeSec: number } } };
    expect(submitted.answer.click.lead).toBe("V1");
    expect(submitted.answer.click.timeSec).toBeGreaterThanOrEqual(0);
    await expect(page.getByRole("heading", { name: /Good decision|Reconsider/ })).toBeVisible();

    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("unsupported guided target fails closed instead of contaminating a receipt", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/practice?focus=ectopy&subskill=apply_in_context&returnTo=/learn/rhythm-ectopy?scene=M03.S14");

    await expect(page.locator(".warning").filter({ hasText: "No automated-screened formative case family can currently support ectopy" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Start shift" })).toBeDisabled();
    await expect(page.getByRole("link", { name: "Return to lesson" })).toHaveAttribute("href", "/learn/rhythm-ectopy?scene=M03.S14");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("guided handoff availability is derived from the live Clinical bank", async ({ page }) => {
    await page.goto("/practice?focus=supraventricular_tachycardia&subskill=apply_in_context");
    await expect(page.getByText(/harness-checked formative target is supraventricular tachycardia/i)).toBeVisible();
    await expect(page.locator(".warning").filter({ hasText: "No automated-screened formative case family" })).toHaveCount(0);
    await page.getByRole("button", { name: "Emergency dept" }).click();
    await page.getByRole("button", { name: "Learn (untimed)" }).click();
    const start = page.getByRole("button", { name: "Start shift" });
    await expect(start).toBeEnabled();
    await start.click();
    await expect(page.getByText("Real de-identified ECG · authored vignette", { exact: true })).toBeVisible();
  });
});
