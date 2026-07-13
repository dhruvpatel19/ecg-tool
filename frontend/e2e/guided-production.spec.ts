import { expect, test } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

test.describe("production guided interactions", () => {
  test("vector evidence and a mechanism explanation complete the native Leads scene", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S1");

    await expect(page.getByRole("heading", { name: "Point the activation vector down and left toward lead II, then predict the dominant sign in lead II and aVR." })).toBeVisible({ timeout: 30_000 });
    const slider = page.getByRole("slider", { name: "Net vector angle" });
    await slider.fill("60");
    await page.getByLabel("II dominant deflection").selectOption("positive");
    await page.getByLabel("aVR dominant deflection").selectOption("negative");
    await page.getByRole("button", { name: "Check my evidence" }).click();

    await expect(page.getByText("The vector points toward lead II and away from aVR", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Continue to the next action" }).click();

    await page.getByLabel("Your explanation").fill("One evolving electrical event looks different because each lead is one of multiple directed views: toward its positive pole is upright and away is downward.");
    await page.getByRole("button", { name: "Check my evidence" }).click();

    await expect(page.getByText("Scene complete · independent evidence recorded")).toBeVisible();
    await expect(page.getByRole("heading", { name: "One event, multiple directed views" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test("a scaffolded contiguous-lead correction cannot masquerade as independent completion", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S9");

    await expect(page.getByRole("heading", { name: "Select the contiguous inferior lead group—and no unrelated views." })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "II", exact: true }).click();
    await page.getByRole("button", { name: "Check my evidence" }).click();
    await expect(page.getByText("You selected part of the inferior group", { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeDisabled();

    await page.getByRole("button", { name: "III", exact: true }).click();
    await page.getByRole("button", { name: "aVF", exact: true }).click();
    await page.getByRole("button", { name: "Check my evidence" }).click();
    await expect(page.getByText("II, III, and aVF are neighboring inferior frontal views.")).toBeVisible();
    await expect(page.getByText("Understanding shown; independent evidence still needed.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeDisabled();
    expect(errors).toEqual([]);
  });

  test("asking the tutor before commitment caps that guided action as assisted", async ({ page }) => {
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await expect(page.getByRole("heading", { name: "Point the activation vector down and left toward lead II, then predict the dominant sign in lead II and aVR." })).toBeVisible({ timeout: 30_000 });

    await page.getByLabel("Message the tutor").fill("Remind me how a lead decides whether this vector is positive or negative.");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("Tutor assistance recorded for this action", { exact: false })).toBeVisible();

    await page.getByRole("slider", { name: "Net vector angle" }).fill("60");
    await page.getByLabel("II dominant deflection").selectOption("positive");
    await page.getByLabel("aVR dominant deflection").selectOption("negative");
    await page.getByRole("button", { name: "Check my evidence" }).click();
    await page.getByRole("button", { name: "Continue to the next action" }).click();
    await page.getByLabel("Your explanation").fill("One electrical event projects positively toward lead II and negatively away from aVR.");
    await page.getByRole("button", { name: "Check my evidence" }).click();

    await expect(page.getByText("Understanding shown; independent evidence still needed.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeDisabled();
    await expect(page.getByText("Scene complete · independent evidence recorded")).toHaveCount(0);
  });

  test("QTc formula scene supplies explicit inputs and accepts both fixed calculations", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/repolarization-safety?scene=m08-s4");

    await expect(page.getByRole("heading", { name: /Given QT 360 ms.*calculate Bazett QTc/ })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("spinbutton", { name: "Bazett QTc ms" }).fill("450");
    await page.getByRole("button", { name: "Check my evidence" }).click();
    await expect(page.getByText(/supplied QT of 360 ms and RR of 640 ms/i)).toBeVisible();
    await page.getByRole("button", { name: "Continue to the next action" }).click();
    await page.getByRole("spinbutton", { name: "Fridericia QTc ms" }).fill("418");
    await page.getByRole("button", { name: "Check my evidence" }).click();
    await expect(page.getByText(/supplied QT of 360 ms and RR of 640 ms/i)).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("a missing ischemia triad fails closed instead of grading a prose proxy", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/ischemia-infarction?scene=m09-s8");

    await expect(page.getByText("Scene locked for this case")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Not independently assessable")).toBeVisible();
    await expect(page.locator(".learning-compare input")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Acknowledge evidence limit & continue" })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
