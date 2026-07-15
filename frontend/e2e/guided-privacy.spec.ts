import { expect, test } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

test("Guided keeps corpus identity and answer fields behind an owner-bound ECG capability", async ({ page }) => {
  await registerVerifiedE2ELearner(page, { prefix: "guided_privacy" });
  const directBackend = process.env.E2E_BACKEND_BASE;
  if (directBackend && !directBackend.endsWith(":8000")) {
    await page.route("**/api/backend/tutorials/**", async (route) => {
      const browserUrl = new URL(route.request().url());
      const backendPath = browserUrl.pathname.replace(/^\/api\/backend/, "");
      const upstream = await route.fetch({
        url: `${directBackend}${backendPath}${browserUrl.search}`,
      });
      await route.fulfill({ response: upstream });
    });
  }
  const selectorResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/backend/tutorials/lead-territories";
  });
  const waveformRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return /^\/api\/backend\/tutorials\/lead-territories\/waveform\/ec_[A-Za-z0-9_-]{43}$/.test(url.pathname);
  });

  await page.goto("/learn/leads-vectors?scene=M02.S1");
  const selector = await selectorResponse;
  expect(selector.ok()).toBe(true);
  const payload = await selector.json() as {
    recommendedCase: { caseId: string; displayId: string; report: string; topConcepts: unknown[] };
    recommendedPacket: Record<string, unknown> & {
      case_id: string;
      ptbxl_plus: { features: Record<string, unknown>; measurements: Record<string, unknown>; fiducials: { rois: unknown[] } };
    };
    guidedContext: string;
    guidedEligibility: { eligible: boolean };
    selection: Record<string, unknown>;
    assessmentPrivacy: Record<string, boolean>;
  };

  expect(payload.recommendedCase.caseId).toMatch(/^ec_[A-Za-z0-9_-]{43}$/);
  expect(payload.guidedContext).toMatch(/^ec_[A-Za-z0-9_-]{43}$/);
  expect(payload.guidedContext).not.toBe(payload.recommendedCase.caseId);
  expect(payload.recommendedCase.displayId).toBe("Guided teaching ECG");
  expect(payload.recommendedCase.report).toBe("");
  expect(payload.recommendedCase.topConcepts).toEqual([]);
  expect(payload.recommendedPacket.case_id).toBe(payload.recommendedCase.caseId);
  expect(payload.recommendedPacket).not.toHaveProperty("ptbxl");
  expect(payload.recommendedPacket).not.toHaveProperty("supported_objectives");
  expect(payload.recommendedPacket).not.toHaveProperty("concept_confidence");
  expect(payload.recommendedPacket.ptbxl_plus.features).toEqual({});
  expect(payload.recommendedPacket.ptbxl_plus.measurements).toEqual({});
  expect(payload.recommendedPacket.ptbxl_plus.fiducials.rois).toEqual([]);
  expect(payload.selection).not.toHaveProperty("targetObjectives");
  expect(payload.selection).not.toHaveProperty("exemplarRejections");
  expect(payload.assessmentPrivacy).toEqual({
    opaqueEcgReference: true,
    answerFieldsWithheldUntilCommit: true,
    sourceRecordIdentityWithheld: true,
  });

  const waveform = await waveformRequest;
  expect(new URL(waveform.url()).pathname).toMatch(
    /^\/api\/backend\/tutorials\/lead-territories\/waveform\/ec_[A-Za-z0-9_-]{43}$/,
  );
  await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
  expect(await page.locator("body").evaluate((body, reference) => body.innerHTML.includes(reference), payload.recommendedCase.caseId)).toBe(false);
  expect(await page.locator("body").evaluate((body, context) => body.innerHTML.includes(context), payload.guidedContext)).toBe(false);
});
