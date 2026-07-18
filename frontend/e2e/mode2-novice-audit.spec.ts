import { test, expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import { registerVerifiedE2ELearner, signInVerifiedE2ELearner } from "./helpers";

const password = "Novice-Audit-2026!";
const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
const learnerA = `novice_a_${suffix}`;
const learnerB = `novice_b_${suffix}`;

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
    packet: { blinded: boolean; source: string };
  };
};

async function register(page: Page, username: string, displayName: string) {
  await registerVerifiedE2ELearner(page, { username, password, displayName });
  await page.goto("/home");
  await expect(page.getByRole("heading", { name: `Welcome back, ${displayName.split(/\s+/)[0]}.` })).toBeVisible({ timeout: 30_000 });
}

async function signIn(page: Page, username: string) {
  await signInVerifiedE2ELearner(page, { username, password });
  await page.goto("/home");
  await expect(page.getByRole("heading", { name: "Welcome back, Novice." })).toBeVisible({ timeout: 30_000 });
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "Sign out of TRACE?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
}

async function openRbbbCompetency(page: Page, displayName: string): Promise<Locator> {
  await page.goto("/home?panel=competencies");
  await expect(page.getByRole("heading", { name: `Welcome back, ${displayName.split(/\s+/)[0]}.` })).toBeVisible({ timeout: 30_000 });

  const panel = page.getByRole("tabpanel", { name: "Progress" });
  await expect(panel.getByRole("heading", { name: "See what's strong and what to practice next" })).toBeVisible({ timeout: 30_000 });
  await panel.getByRole("searchbox", { name: "Search skills" }).fill("right bundle branch block");

  const competencyMap = panel
    .getByRole("heading", { name: "Browse all skills" })
    .locator("xpath=ancestor::section[1]");
  const matchingDetails = competencyMap.locator("details").filter({
    has: page.getByText("Right bundle branch block", { exact: true }),
  });
  const domain = matchingDetails.first();
  await expect(domain.locator(":scope > summary")).toBeVisible({ timeout: 30_000 });
  await domain.locator(":scope > summary").click();

  const objective = domain.locator("details").filter({
    has: page.getByText("Right bundle branch block", { exact: true }),
  }).first();
  await expect(objective.locator(":scope > summary")).toBeVisible({ timeout: 30_000 });
  return objective;
}

async function readRbbbStartedSkills(page: Page, displayName: string) {
  const trackedObjective = await openRbbbCompetency(page, displayName);
  const skillCount = trackedObjective.locator(":scope > summary small");
  const summary = await skillCount.innerText();
  const match = summary.match(/^(\d+)(?: of \d+)? skills? (?:with evidence|practiced)$/);
  const evidenceCount = ["No recorded skill evidence", "No skills practiced yet"].includes(summary)
    ? 0
    : Number(match?.[1]);
  if (!Number.isFinite(evidenceCount)) throw new Error("The RBBB finding summary did not expose its skill-evidence count.");
  await page.goto("/home");
  await expect(page.getByRole("heading", { name: `Welcome back, ${displayName.split(/\s+/)[0]}.` })).toBeVisible({ timeout: 30_000 });
  return evidenceCount;
}

async function captureAuditScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string,
  fullPage = true,
) {
  await expect(page.locator('[data-route-accessibility-ready="true"]')).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath(name), fullPage });
}

test.describe.serial("novice Mode 2 audit", () => {
  test("desktop learner journey, tutor, adaptive repetition, and two-account isolation", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/login?next=/train");
    await captureAuditScreenshot(page, testInfo, "login-desktop.png");

    await register(page, learnerA, "Novice A");
    const initialA = await readRbbbStartedSkills(page, "Novice A");
    console.log("AUDIT initial learner A RBBB skills", initialA);
    await captureAuditScreenshot(page, testInfo, "first-dashboard.png");

    const poolResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/pool")
        && url.searchParams.get("conceptId") === "right_bundle_branch_block";
    });
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    const pool = await (await poolResponse).json() as { eligibleDistinct: number; roleCounts: { target: number; mimic: number; negative: number } };
    await expect(page.getByLabel("Target concept")).toHaveValue("right_bundle_branch_block");
    const subskills = await page.getByLabel("Skill to practice").locator("option").allTextContents();
    console.log("AUDIT immutable pool", pool);
    console.log("AUDIT subskills", subskills);
    expect(pool.eligibleDistinct).toBeGreaterThanOrEqual(10);
    expect(pool.roleCounts.target).toBeGreaterThan(0);
    await expect(page.getByText(`${pool.eligibleDistinct.toLocaleString()} unique ECGs available`)).toBeVisible();
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);
    await expect(page.getByText("Reviewed real ECG waveforms only")).toBeVisible();
    await captureAuditScreenshot(page, testInfo, "train-desktop-before.png");

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start training" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.campaign?.requestedLength).toBe(10);
    expect(started.campaign?.length).toBeLessThanOrEqual(pool.eligibleDistinct);
    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    const firstCaseId = started.current?.case.caseId;
    expect(firstCaseId).toBeTruthy();
    expect(started.campaign?.status).toBe("active");
    expect(started.campaign?.pendingCaseId).toBe(firstCaseId);
    expect(started.campaign?.poolCount).toBe(pool.eligibleDistinct);
    await expect(page.getByRole("region", { name: "Configure training set" })).toHaveCount(0);
    await expect(page.getByLabel("Target concept")).toHaveCount(0);
    await expect(page.getByLabel("Skill to practice")).toHaveCount(0);
    const activeSet = page.getByRole("region", { name: "Focused training set" });
    await expect(activeSet).toContainText("Case 1");
    await expect(activeSet).toContainText(`of ${started.campaign?.length.toLocaleString()}`);

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Commit answer" }).click();
    await submitResponse;
    await expect(page.getByRole("heading", { name: /Pattern recognized|Contrast distinguished|Decision supported|Re-check the discriminator/ })).toBeVisible({ timeout: 60_000 });
    const answerEvidence = page.getByRole("region", { name: "Answer evidence" });
    await expect(answerEvidence.getByRole("heading", { name: "Why this answer" })).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toBeHidden();
    await page.getByRole("button", { name: "Open tutor" }).click();
    const tutorDialog = page.getByRole("dialog", { name: "ECG tutor" });
    await expect(tutorDialog).toBeVisible();
    await expect(tutorDialog.getByLabel("Message the tutor")).toBeVisible();
    await captureAuditScreenshot(page, testInfo, "feedback-tutor.png");

    await tutorDialog.getByLabel("Message the tutor").fill("I am a first-year student: why does V1 matter here, and how is this different from LBBB?");
    const tutorRepliesBefore = await tutorDialog.locator(".chat-bubble.tutor").count();
    await tutorDialog.getByRole("button", { name: "Send", exact: true }).click();
    await expect(tutorDialog.locator(".chat-bubble.tutor")).toHaveCount(tutorRepliesBefore + 1, { timeout: 60_000 });
    await expect(tutorDialog.locator(".chat-bubble.tutor").last()).toContainText(/V1|LBBB|Left bundle branch block/i, { timeout: 60_000 });
    await captureAuditScreenshot(page, testInfo, "tutor-answer.png");
    await tutorDialog.getByRole("button", { name: "Close tutor" }).click();

    const adaptiveResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next") && response.ok());
    await page.getByRole("button", { name: /Next case in set/ }).click();
    const advanced = await (await adaptiveResponse).json() as CampaignPayload;
    const secondCaseId = advanced.current?.case.caseId;
    console.log("AUDIT adaptive case transition", { changed: firstCaseId !== secondCaseId });
    expect(advanced.current?.kind).toBe("pending");
    expect(advanced.current?.packet.blinded).toBe(true);
    expect(secondCaseId).not.toBe(firstCaseId);
    expect(advanced.campaign?.campaignId).toBe(started.campaign?.campaignId);
    expect(advanced.campaign?.requestedLength).toBe(started.campaign?.requestedLength);
    expect(advanced.campaign?.length).toBe(started.campaign?.length);
    expect(advanced.campaign?.pendingCaseId).toBe(secondCaseId);
    await expect(page.getByRole("region", { name: "Focused training set" })).toContainText("Case 2");
    // The frozen campaign roster owns the active workspace. Configuration is
    // intentionally absent until the learner deliberately abandons the set.
    await expect(page.getByRole("region", { name: "Configure training set" })).toHaveCount(0);
    await expect(page.getByLabel("Skill to practice")).toHaveCount(0);
    await expect(page.getByText(/This lesson target is locked/)).toHaveCount(0);

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Leave training set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    await abandonResponse;
    await expect(page.getByLabel("Skill to practice")).toBeEnabled();
    const localizePoolResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/pool") && url.searchParams.get("subskill") === "localize";
    });
    await page.getByLabel("Skill to practice").selectOption("localize");
    await localizePoolResponse;
    await expect(page.getByRole("button", { name: "Start training" })).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);
    await captureAuditScreenshot(page, testInfo, "localize-desktop.png");

    const afterA = await readRbbbStartedSkills(page, "Novice A");
    expect(afterA).toBeGreaterThan(0);
    console.log("AUDIT learner A RBBB skills after training", afterA);
    await signOut(page);
    await register(page, learnerB, "Novice B");
    const initialB = await readRbbbStartedSkills(page, "Novice B");
    console.log("AUDIT initial learner B RBBB skills", initialB);
    await captureAuditScreenshot(page, testInfo, "account-b-dashboard.png");
    expect(initialB).toBe(0);

    await signOut(page);
    await signIn(page, learnerA);
    const restoredA = await readRbbbStartedSkills(page, "Novice A");
    console.log("AUDIT restored learner A RBBB skills", restoredA);
    expect(restoredA).not.toBeNull();
    expect(restoredA!).toBeGreaterThan(initialB ?? 0);
    const trackedObjective = await openRbbbCompetency(page, "Novice A");
    const objectiveSummary = trackedObjective.locator(":scope > summary");
    await expect(objectiveSummary).toContainText("1 of 8 skills practiced");
    await expect(objectiveSummary).toContainText("Scored check available");
    await expect(objectiveSummary).not.toContainText("Checked on real ECGs");
    await objectiveSummary.click();
    await expect(trackedObjective.getByText(
      "You've completed formative practice for this skill. Complete a scored ECG check to measure your progress.",
      { exact: true },
    )).toBeVisible();
    await captureAuditScreenshot(page, testInfo, "profile-after-attempt.png");
  });

  test("mobile 390x844 layout and keyboard-first focus reach the core controls", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page, learnerA);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=measure");
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Skill to practice")).toHaveValue("measure");
    await expect(page.getByLabel("Skill to practice")).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start training" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.current?.packet.blinded).toBe(true);
    await expect(page.getByRole("heading", { name: "Measure it" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("region", { name: "Configure training set" })).toHaveCount(0);
    await expect(page.getByLabel("Skill to practice")).toHaveCount(0);
    const geometry = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      targetTop: (document.querySelector("#train-target") as HTMLElement | null)?.getBoundingClientRect().top ?? null,
      commitTop: (document.querySelector(".train-commit-button") as HTMLElement | null)?.getBoundingClientRect().top ?? null,
      overflowElements: [...document.querySelectorAll<HTMLElement>("body *")]
        // The ECG SVG intentionally uses an 880-unit internal viewBox and is
        // clipped responsively. Only HTML boxes can create document overflow.
        .filter((el) => el.namespaceURI === "http://www.w3.org/1999/xhtml")
        .map((el) => ({ tag: el.tagName, className: el.className?.toString().slice(0, 100), right: Math.round(el.getBoundingClientRect().right), width: Math.round(el.getBoundingClientRect().width), scrollWidth: el.scrollWidth }))
        .filter((item) => item.right > window.innerWidth + 2)
        .slice(0, 20),
    }));
    console.log("AUDIT mobile geometry", geometry);
    await captureAuditScreenshot(page, testInfo, "train-mobile-top.png", false);
    await captureAuditScreenshot(page, testInfo, "train-mobile-full.png");

    await page.keyboard.press("Home");
    const focusTrail: string[] = [];
    for (let index = 0; index < 60; index += 1) {
      await page.keyboard.press("Tab");
      focusTrail.push(await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el) return "none";
        const label = el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent : null;
        return `${el.tagName}:${el.getAttribute("aria-label") ?? label ?? el.innerText ?? el.id}`.slice(0, 120);
      }));
    }
    console.log("AUDIT mobile focus trail", focusTrail);
    // Campaign setup is deliberately absent in the trace-first workspace,
    // while the active task, precise-entry fallback, and escape control remain
    // keyboard reachable.
    expect(focusTrail.some((item) => item.includes("Target present"))).toBeTruthy();
    expect(focusTrail.some((item) => item.includes("Keyboard / precise-entry alternative"))).toBeTruthy();
    expect(focusTrail.some((item) => item.includes("Confidence"))).toBeTruthy();
    expect(focusTrail.some((item) => item.includes("Leave training set"))).toBeTruthy();
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.innerWidth + 2);
    expect(geometry.overflowElements).toEqual([]);

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Leave training set" }).click();
    await page.getByRole("button", { name: "Leave set and change setup" }).click();
    await abandonResponse;
  });

  test("registration validation explains a weak password accurately", async ({ page }, testInfo) => {
    await page.goto("/login");
    await page.getByRole("tab", { name: "Register" }).click();
    await page.getByLabel("Email").fill(`shortpw_${suffix}@example.test`);
    await page.getByRole("textbox", { name: "Password", exact: true }).fill("x");
    await page.getByRole("textbox", { name: "Confirm password", exact: true }).fill("x");
    await page.getByRole("button", { name: "Create account" }).click();
    const warning = page.locator("#auth-password-error");
    await expect(warning).toHaveText("Use at least 10 characters.");
    console.log("AUDIT weak-password message", await warning.innerText());
    await captureAuditScreenshot(page, testInfo, "register-validation.png");
  });
});
