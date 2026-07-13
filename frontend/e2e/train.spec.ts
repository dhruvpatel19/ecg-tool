import { test, expect, type Page } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

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
    case: { caseId: string };
    packet: {
      blinded: boolean;
      source: string;
      supported_objectives?: string[];
      concept_confidence?: Record<string, unknown>;
      ptbxl_plus: { fiducials: { rois: Array<{ lead: string; concept: string; timeStartSec: number; timeEndSec: number }> } };
    };
  };
  answer?: {
    grade: { masteryDelta: Record<string, number>; legacyObjectiveMasterySuppressed: boolean };
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
    await abandonActiveCampaign(page);
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

    await expect(page.getByRole("heading", { name: "Choose how far you want to train" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Requested unique ECGs").locator("option")).toHaveText([
      "10", "25", "50", "100", "500", "1,000", "5,000",
    ]);
    await expect(page.getByText(`${pool.eligibleDistinct.toLocaleString()} distinct eligible`)).toBeVisible();
    expect(pool.source).toBe("audited_waveform_only");
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);

    await page.getByLabel("Requested unique ECGs").selectOption("5000");
    if (pool.eligibleDistinct < 5000) {
      await expect(page.getByText(new RegExp(`capped at ${pool.eligibleDistinct.toLocaleString()}`, "i"))).toBeVisible();
      await expect(page.getByText(/no synthetic or repeated case will fill the gap/i)).toBeVisible();
    }

    await page.getByLabel("Target concept").selectOption("sinus_rhythm");
    await page.getByLabel("Target subskill").selectOption("measure");
    const setup = page.getByRole("region", { name: "Configure Training campaign" });
    await expect(setup.getByRole("status")).toContainText(/No distinct audited Tier A\/B waveform ECGs currently satisfy this concept and subskill contract/i);
    await expect(setup.getByRole("status")).toContainText(/Choose another subskill or concept to continue/i);
    await expect(page.getByRole("button", { name: "Start immutable campaign" })).toBeDisabled();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("persists, resumes, grades exactly once, advances without a repeat, and abandons", async ({ page }) => {
    test.setTimeout(120_000);
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("button", { name: "Start immutable campaign" })).toBeEnabled({ timeout: 30_000 });

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start immutable campaign" }).click();
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

    await expect(page.getByRole("region", { name: "Focused training campaign" })).toContainText("Case 1", { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Tutor on the back burner" })).toBeVisible();

    const activeResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/api/backend/training/campaigns/active"));
    await page.reload();
    const resumed = await (await activeResponse).json() as CampaignPayload;
    expect(resumed.current?.case.caseId).toBe(firstCaseId);
    await expect(page.getByText(/Resumed your server-owned campaign/i)).toBeVisible({ timeout: 30_000 });

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Commit target decision" }).click();
    const submitted = await (await submitResponse).json() as CampaignPayload;
    expect(submitted.answer?.grade.masteryDelta).toEqual({});
    expect(submitted.answer?.grade.legacyObjectiveMasterySuppressed).toBe(true);
    expect(submitted.replay).toBe(false);
    await expect(page.getByRole("heading", { name: "Grounded reveal" })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByLabel("Message the tutor")).toBeVisible();

    const nextResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next"));
    await page.getByRole("button", { name: /Next case in set/ }).click();
    const advanced = await (await nextResponse).json() as CampaignPayload;
    expect(advanced.current?.case.caseId).not.toBe(firstCaseId);
    await expect(page.getByRole("region", { name: "Focused training campaign" })).toContainText("Case 2");

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Abandon campaign" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "Choose how far you want to train" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("focused WCT campaigns expose all 130 expert targets and open on a Leipzig rhythm window", async ({ page }) => {
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
      `${pool.roleCounts.target.toLocaleString()} target-positive · ${pool.roleCounts.mimic.toLocaleString()} close-mimic · ${pool.roleCounts.negative.toLocaleString()} other negative`,
    )).toBeVisible({ timeout: 30_000 });

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start immutable campaign" }).click();
    const started = await (await startResponse).json() as CampaignPayload;

    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    expect(started.current?.packet.source).toBe("leipzig-heart-center");
    expect(started.current?.case.caseId).toMatch(/^leipzig-heart-center:/);
    await expect(page.getByRole("region", { name: "ECG provenance" })).toContainText("Leipzig expert rhythm window", { timeout: 30_000 });
    await expect(page.getByRole("region", { name: "Focused training campaign" })).toContainText("Case 1");

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Abandon campaign" }).click();
    expect((await abandonResponse).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "Choose how far you want to train" })).toBeVisible();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("measure campaigns retain the keyboard-accessible trace-native evidence gate", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=measure");
    await expect(page.getByRole("button", { name: "Start immutable campaign" })).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start immutable campaign" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    const qrs = started.current?.packet.ptbxl_plus.fiducials.rois.find(
      (roi) => roi.concept === "qrs_complex" && ["V1", "V6"].includes(roi.lead),
    );
    expect(qrs).toBeTruthy();

    await expect(page.getByRole("heading", { name: "Measure it" })).toBeVisible({ timeout: 30_000 });
    await page.getByText("Keyboard / precise-entry alternative").click();
    await page.locator(".viewer-keyboard-fields select").selectOption(qrs!.lead);
    await page.getByLabel("First boundary (seconds)").fill(qrs!.timeStartSec.toFixed(3));
    await page.getByLabel("Second boundary (seconds)").fill(qrs!.timeEndSec.toFixed(3));
    await page.getByRole("button", { name: "Use these caliper boundaries" }).click();
    await expect(page.getByText(/boundaries overlap the reviewed waveform region/i)).toBeVisible();
    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    await expect(page.getByRole("button", { name: "Commit target decision" })).toBeEnabled();
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("mechanism handoff opens a reviewed server-graded choice task", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/train?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=explain_mechanism&returnTo=/review");
    await expect(page.getByRole("button", { name: "Start immutable campaign" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start immutable campaign" }).click();
    await expect(page.getByText("Exact explain mechanism task")).toBeVisible({ timeout: 30_000 });
    const mechanism = page.getByRole("radiogroup", { name: /Which causal chain best explains/i });
    await expect(mechanism).toBeVisible();
    await expect(mechanism.getByRole("radio")).toHaveCount(4);
    await expect(page.getByText(/does not infer symptoms, acuity, etiology, or treatment/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /Return/i })).toHaveAttribute("href", "/review");
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
