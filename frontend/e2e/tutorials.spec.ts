import { test, expect } from "@playwright/test";

test.describe("tutorials", () => {
  test("open a lesson, render the viewer, chat with the tutor", async ({ page }) => {
    await page.goto("/tutorials");

    // The ECG viewer renders once the recommended case loads.
    await expect(page.getByRole("img", { name: /12-lead ECG/i })).toBeVisible({ timeout: 30_000 });

    // Lesson steps panel is present.
    await expect(page.getByRole("heading", { name: "Lesson Steps" })).toBeVisible();

    // Send a tutor chat message.
    const composer = page.getByLabel("Message the tutor");
    await expect(composer).toBeVisible();
    await composer.fill("What is the heart rate on this ECG?");
    await page.getByRole("button", { name: "Send" }).click();

    // The user's turn is echoed.
    await expect(page.locator(".chat-bubble.user").last()).toContainText("heart rate", { timeout: 15_000 });

    // A tutor reply bubble appears (typewriter reveal fills it in).
    const tutorBubble = page.locator(".chat-bubble.tutor").last();
    await expect(tutorBubble).toBeVisible({ timeout: 45_000 });
    await expect(tutorBubble.locator(".chat-text")).not.toHaveText("", { timeout: 45_000 });
  });
});
