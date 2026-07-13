import { test, expect, type Page } from "@playwright/test";

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
  await page.goto("/login");
  await page.getByRole("button", { name: "Register" }).click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Display name (optional)").fill(displayName);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toBeVisible({ timeout: 30_000 });
}

async function signIn(page: Page, username: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.locator("form").getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toBeVisible({ timeout: 30_000 });
}

async function readAttemptsCard(page: Page) {
  const card = page.locator(".insight-item").filter({ hasText: "Completed reads" });
  await expect(card).toBeVisible();
  const value = await card.locator("strong").innerText();
  return Number(value);
}

test.describe.serial("novice Mode 2 audit", () => {
  test("desktop learner journey, tutor, adaptive repetition, and two-account isolation", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/login?next=/train");
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-login-desktop.png", fullPage: true });

    await register(page, learnerA, "Novice A");
    const initialA = await readAttemptsCard(page);
    console.log("AUDIT initial learner A attempts", initialA);
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-first-dashboard.png", fullPage: true });

    const poolResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/pool")
        && url.searchParams.get("conceptId") === "right_bundle_branch_block";
    });
    await page.goto("/train?concept=right_bundle_branch_block");
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    const pool = await (await poolResponse).json() as { eligibleDistinct: number; roleCounts: { target: number; mimic: number; negative: number } };
    await expect(page.getByLabel("Target concept")).toHaveValue("right_bundle_branch_block");
    const subskills = await page.getByLabel("Target subskill").locator("option").allTextContents();
    console.log("AUDIT immutable pool", pool);
    console.log("AUDIT subskills", subskills);
    expect(pool.eligibleDistinct).toBeGreaterThanOrEqual(10);
    expect(pool.roleCounts.target).toBeGreaterThan(0);
    await expect(page.getByText(`${pool.eligibleDistinct.toLocaleString()} distinct eligible`)).toBeVisible();
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);
    await expect(page.getByText(/first blinded ECG appears only after the server has persisted the full unique-case ledger/i)).toBeVisible();
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-train-desktop-before.png", fullPage: true });

    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start immutable campaign" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.campaign?.requestedLength).toBe(10);
    expect(started.campaign?.length).toBeLessThanOrEqual(pool.eligibleDistinct);
    expect(started.current?.kind).toBe("pending");
    expect(started.current?.packet.blinded).toBe(true);
    const firstCaseId = started.current?.case.caseId;
    expect(firstCaseId).toBeTruthy();
    await expect(page.getByLabel("Target concept")).toBeDisabled();
    await expect(page.getByLabel("Target subskill")).toBeDisabled();
    await expect(page.getByRole("region", { name: "Focused training campaign" })).toContainText("Case 1");

    await page.getByRole("group", { name: "Target decision" }).getByRole("button").first().click();
    const submitResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/submit"));
    await page.getByRole("button", { name: "Commit target decision" }).click();
    await submitResponse;
    await expect(page.getByRole("heading", { name: /Contrast caught|Re-check the discriminator/ })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("heading", { name: "Grounded reveal" })).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toBeVisible();
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-feedback-tutor.png", fullPage: true });

    await page.getByLabel("Message the tutor").fill("I am a first-year student: why does V1 matter here, and how is this different from LBBB?");
    const tutorRepliesBefore = await page.locator(".chat-bubble.tutor").count();
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.locator(".chat-bubble.tutor")).toHaveCount(tutorRepliesBefore + 1, { timeout: 60_000 });
    await expect(page.locator(".chat-bubble.tutor").last()).toContainText(/V1|LBBB|Left bundle branch block/i, { timeout: 60_000 });
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-tutor-answer.png", fullPage: true });

    const adaptiveResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/next") && response.ok());
    await page.getByRole("button", { name: /Next case in set/ }).click();
    const advanced = await (await adaptiveResponse).json() as CampaignPayload;
    const secondCaseId = advanced.current?.case.caseId;
    console.log("AUDIT adaptive case transition", { firstCaseId, secondCaseId });
    expect(advanced.current?.kind).toBe("pending");
    expect(advanced.current?.packet.blinded).toBe(true);
    expect(secondCaseId).not.toBe(firstCaseId);
    await expect(page.getByRole("region", { name: "Focused training campaign" })).toContainText("Case 2");
    // The full ledger owns its target while active. A normal concept deep link
    // becomes editable again only after the learner deliberately abandons it.
    await expect(page.getByLabel("Target subskill")).toBeDisabled();
    await expect(page.getByText(/This lesson target is locked/)).toHaveCount(0);

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Abandon campaign" }).click();
    await abandonResponse;
    await expect(page.getByLabel("Target subskill")).toBeEnabled();
    const localizePoolResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns/pool") && url.searchParams.get("subskill") === "localize";
    });
    await page.getByLabel("Target subskill").selectOption("localize");
    await localizePoolResponse;
    await expect(page.getByRole("button", { name: "Start immutable campaign" })).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByRole("group", { name: "Target decision" })).toHaveCount(0);
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-localize-desktop.png", fullPage: true });

    await page.goto("/");
    await expect.poll(() => readAttemptsCard(page), { timeout: 15_000 }).toBeGreaterThan(0);
    const afterA = await readAttemptsCard(page);
    console.log("AUDIT learner A attempts after training", afterA);
    await page.getByRole("button", { name: "Sign out" }).click();
    await register(page, learnerB, "Novice B");
    const initialB = await readAttemptsCard(page);
    console.log("AUDIT initial learner B attempts", initialB);
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-account-b-dashboard.png", fullPage: true });
    expect(initialB).toBe(0);

    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, learnerA);
    await expect.poll(() => readAttemptsCard(page), { timeout: 15_000 }).toBeGreaterThan(0);
    const restoredA = await readAttemptsCard(page);
    console.log("AUDIT restored learner A attempts", restoredA);
    expect(restoredA).not.toBeNull();
    expect(restoredA!).toBeGreaterThan(initialB ?? 0);
    await page.goto("/profile");
    await expect(page.getByRole("heading", { name: "Novice A progress" })).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("Find a competency").fill("right bundle branch block");
    await expect(page.locator(".profile-objective").filter({ hasText: /Right bundle branch block/i }).first()).toBeVisible();
    await expect(page.getByText(/Saved to Novice A's profile/i)).toBeVisible();
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-profile-after-attempt.png", fullPage: true });
  });

  test("mobile 390x844 layout and keyboard-first focus reach the core controls", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page, learnerA);
    await page.goto("/train?concept=right_bundle_branch_block&subskill=measure");
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Target subskill")).toHaveValue("measure");
    await expect(page.getByLabel("Target subskill")).toBeEnabled({ timeout: 30_000 });
    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/api/backend/training/campaigns") && response.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Start immutable campaign" }).click();
    const started = await (await startResponse).json() as CampaignPayload;
    expect(started.current?.packet.blinded).toBe(true);
    await expect(page.getByRole("heading", { name: "Measure it" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Target subskill")).toBeDisabled({ timeout: 30_000 });
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
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-train-mobile-top.png" });
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-train-mobile-full.png", fullPage: true });

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
    // Campaign-owned selectors are deliberately disabled (and therefore not
    // tabbable), while the active task, precise-entry fallback, and escape
    // control must remain keyboard reachable.
    expect(focusTrail.some((item) => item.includes("Target present"))).toBeTruthy();
    expect(focusTrail.some((item) => item.includes("Keyboard / precise-entry alternative"))).toBeTruthy();
    expect(focusTrail.some((item) => item.includes("Confidence"))).toBeTruthy();
    expect(focusTrail.some((item) => item.includes("Abandon campaign"))).toBeTruthy();
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.innerWidth + 2);
    expect(geometry.overflowElements).toEqual([]);

    const abandonResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/abandon"));
    await page.getByRole("button", { name: "Abandon campaign" }).click();
    await abandonResponse;
  });

  test("registration validation explains a weak password accurately", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Register" }).click();
    await page.getByLabel("Username").fill(`shortpw_${suffix}`.slice(0, 31));
    await page.getByLabel("Password").fill("x");
    await page.getByRole("button", { name: "Create account" }).click();
    const warning = page.locator(".warning");
    await expect(warning).toBeVisible();
    console.log("AUDIT weak-password message", await warning.innerText());
    await page.screenshot({ path: "../docs/persona-tests/mode2-novice-register-validation.png", fullPage: true });
  });
});
