import { expect, test } from "@playwright/test";
import { collectConsoleErrors, completeAuthoredModel, registerVerifiedE2ELearner } from "./helpers";

test.describe("production guided interactions", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "guided_production" });
  });

  test("announces a failed ECG load and retries the same guided checkpoint in place", async ({ page }) => {
    let tutorialChecks = 0;
    let allowRecovery = false;
    await page.route("**/api/backend/tutorials/*", async (route) => {
      tutorialChecks += 1;
      if (!allowRecovery) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporarily unavailable" }) });
        return;
      }
      await route.continue();
    });

    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await completeAuthoredModel(page);
    const recovery = page.getByRole("alert").filter({ hasText: /This ECG could not load/i });
    await expect(recovery).toBeVisible({ timeout: 30_000 });
    allowRecovery = true;
    await recovery.getByRole("button", { name: "Retry ECG" }).click();

    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });
    await expect(recovery).toHaveCount(0);
    expect(tutorialChecks).toBeGreaterThanOrEqual(2);
  });

  test("Guidance preferences preserve the authored model and unchanged ECG task", async ({ page }) => {
    const saved = await page.request.put("/api/backend/learning/preferences", {
      data: { guidanceLevel: "step_by_step" },
    });
    expect(saved.ok()).toBe(true);
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await expect(page.getByRole("heading", { name: "Why does one beat look different twelve times?" })).toBeVisible({ timeout: 30_000 });

    const studio = page.getByRole("region", { name: "Build the spatial model" });
    await expect(studio.getByText("The module owns", { exact: true })).toBeVisible();
    await expect(studio.getByRole("navigation", { name: "Lesson ideas" }).getByRole("button")).toHaveCount(4);
    await expect(page.locator("#production-active-interaction")).toHaveCount(0);

    const minimal = await page.request.put("/api/backend/learning/preferences", {
      data: { guidanceLevel: "minimal" },
    });
    expect(minimal.ok()).toBe(true);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Why does one beat look different twelve times?" })).toBeVisible({ timeout: 30_000 });
    await expect(studio.getByText("The module owns", { exact: true })).toBeVisible();
    await expect(studio.getByRole("navigation", { name: "Lesson ideas" }).getByRole("button")).toHaveCount(4);
    await expect(page.locator("#production-active-interaction")).toHaveCount(0);
  });

  test("vector evidence and a mechanism explanation complete the native Leads scene", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await completeAuthoredModel(page);

    await expect(page.getByRole("heading", { name: "Point the activation vector down and left toward lead II, then predict the dominant sign in lead II and aVR." })).toBeVisible({ timeout: 30_000 });
    const slider = page.getByRole("slider", { name: "Net vector angle" });
    await slider.fill("60");
    await page.getByLabel("II dominant deflection").selectOption("positive");
    await page.getByLabel("aVR dominant deflection").selectOption("negative");
    await page.getByRole("button", { name: "Check answer" }).click();

    await expect(page.getByText("The vector points toward lead II and away from aVR", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Continue" }).click();

    await page.getByLabel("Your explanation").fill("One evolving electrical event looks different because each lead is one of multiple directed views: toward its positive pole is upright and away is downward.");
    await page.getByRole("button", { name: "Check answer" }).click();

    await expect(page.getByText("Lesson complete · practice saved")).toBeVisible();
    await expect(page.getByText(/Practice saved.*fresh mixed ECG/i)).toBeVisible();
    await expect(page.getByText("Scene complete · progress updated")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "One event, multiple directed views" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test("a scaffolded contiguous-lead correction cannot masquerade as independent completion", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S9");
    await completeAuthoredModel(page);

    await expect(page.getByRole("heading", { name: "Select the contiguous inferior lead group—and no unrelated views." })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "II", exact: true }).click();
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.getByText("You selected part of the inferior group", { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeDisabled();

    await page.getByRole("button", { name: "III", exact: true }).click();
    await page.getByRole("button", { name: "aVF", exact: true }).click();
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.getByText("II, III, and aVF are neighboring inferior frontal views.")).toBeVisible();
    await expect(page.getByText("Nice work with support.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeDisabled();
    expect(errors).toEqual([]);
  });

  test("asking the tutor before commitment caps that guided action as assisted", async ({ page }) => {
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await completeAuthoredModel(page);
    await expect(page.getByRole("heading", { name: "Point the activation vector down and left toward lead II, then predict the dominant sign in lead II and aVR." })).toBeVisible({ timeout: 30_000 });

    const tutorTrigger = page.getByRole("button", { name: "Ask Luna", exact: true });
    await tutorTrigger.click();
    await expect(page.getByRole("dialog", { name: /tutor/i })).toBeVisible();
    await page.getByLabel("Message the tutor").fill("Remind me how a lead decides whether this vector is positive or negative.");
    await page.getByRole("button", { name: "Send" }).click();
    await page.keyboard.press("Escape");
    await expect(tutorTrigger).toBeFocused();
    await expect(page.getByText("Tutor help noted.", { exact: false })).toBeVisible();

    await page.getByRole("slider", { name: "Net vector angle" }).fill("60");
    await page.getByLabel("II dominant deflection").selectOption("positive");
    await page.getByLabel("aVR dominant deflection").selectOption("negative");
    await page.getByRole("button", { name: "Check answer" }).click();
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Your explanation").fill("One electrical event projects positively toward lead II and negatively away from aVR.");
    await page.getByRole("button", { name: "Check answer" }).click();

    await expect(page.getByText("Nice work with support.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeDisabled();
    await expect(page.getByText("Scene complete · progress updated")).toHaveCount(0);
  });

  test("a failed tutor request preserves the question and does not mark the action assisted", async ({ page }) => {
    await page.route("**/api/backend/tutor/message", async (route) => {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "unavailable" }) });
    });
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await completeAuthoredModel(page);
    await expect(page.getByRole("heading", { name: "Point the activation vector down and left toward lead II, then predict the dominant sign in lead II and aVR." })).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: "Ask Luna", exact: true }).click();
    const question = "How should I decide whether this vector is positive?";
    await page.getByLabel("Message the tutor").fill(question);
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(/Your question is still here/i)).toBeVisible();
    await expect(page.getByLabel("Message the tutor")).toHaveValue(question);
    await expect(page.getByText("Tutor help noted.", { exact: false })).toHaveCount(0);
  });

  test("staged clinical decisions reveal sequentially and lock committed answers", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S13");
    await completeAuthoredModel(page);

    await expect(page.getByRole("heading", { name: "Compare a verified stable variant with a teaching example of electrode misplacement." })).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("Prior relationship, stable r wave progression variant").selectOption({ label: "stable on prior" });
    await page.getByLabel("Prior relationship, precordial lead misplacement").selectOption({ label: "changed after placement" });
    await page.getByLabel("Best category, stable r wave progression variant").selectOption({ label: "plausible variation" });
    await page.getByLabel("Best category, precordial lead misplacement").selectOption({ label: "possible placement problem" });
    await page.getByLabel("Next check, stable r wave progression variant").selectOption({ label: "describe and retain context" });
    await page.getByLabel("Next check, precordial lead misplacement").selectOption({ label: "verify electrode position" });
    await page.getByRole("button", { name: "Check answer" }).click();
    await page.getByRole("button", { name: "Continue" }).click();

    const firstChoice = page.getByRole("button", { name: "Possible right-arm/left-arm reversal; verify acquisition." });
    const secondStage = page.getByRole("group", { name: "Stage 2 · Unusual progression is stable on a correctly acquired prior" });
    await expect(firstChoice).toBeVisible();
    await expect(secondStage).toHaveCount(0);
    await firstChoice.click();
    await expect(secondStage).toHaveCount(0);
    await page.getByRole("button", { name: "Commit stage and reveal next" }).click();

    await expect(firstChoice).toBeDisabled();
    await expect(page.getByText("Decision committed. This stage is locked.", { exact: true })).toBeVisible();
    await expect(secondStage).toBeVisible();
    await expect(page.getByRole("button", { name: "Check answer" })).toBeDisabled();
    const secondChoice = page.getByRole("button", { name: "Plausible stable variation; describe and retain context." });
    await secondChoice.click();
    await page.getByRole("button", { name: "Commit final stage" }).click();
    await expect(secondChoice).toBeDisabled();
    await expect(page.getByText("All staged decisions are committed. Check your evidence when ready.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Check answer" })).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test("QTc formula scene supplies explicit inputs and accepts both fixed calculations", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/repolarization-safety?scene=m08-s4");
    await completeAuthoredModel(page);

    await expect(page.getByRole("heading", { name: /Given QT 360 ms.*calculate Bazett QTc/ })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("spinbutton", { name: "Bazett QTc ms" }).fill("450");
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.getByText(/supplied QT of 360 ms and RR of 640 ms/i)).toBeVisible();
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("spinbutton", { name: "Fridericia QTc ms" }).fill("418");
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.getByText(/supplied QT of 360 ms and RR of 640 ms/i)).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("a missing ischemia triad fails closed instead of grading a prose proxy", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/ischemia-infarction?scene=m09-s8");
    await completeAuthoredModel(page);

    await expect(page.getByText("Tracing unavailable", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("This ECG check is not available right now.", { exact: true })).toBeVisible();
    await expect(page.locator(".learning-compare input")).toHaveCount(0);
    await expect(page.locator(".learning-compare select")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Review later and continue" })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
