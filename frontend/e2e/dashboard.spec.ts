import { test, expect } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

test.describe("dashboard", () => {
  test("presents the four-mode product and routes into each mode", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Choose the kind of work you need." })).toBeVisible();

    const modeLinks = [
      { name: /Continue learning/, href: "/learn" },
      { name: /Open competency lab/, href: "/train" },
      { name: /Start a rapid read/, href: "/rapid" },
      { name: /Enter clinical cases/, href: "/practice" },
    ];
    for (const mode of modeLinks) {
      await expect(page.getByRole("link", { name: mode.name })).toHaveAttribute("href", mode.href);
    }

    const primary = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primary.getByRole("link", { name: /Guided learning/ })).toBeVisible();
    await expect(primary.getByRole("link", { name: /Competency lab/ })).toBeVisible();
    await expect(primary.getByRole("link", { name: /Rapid reads/ })).toBeVisible();
    await expect(primary.getByRole("link", { name: /Clinical cases/ })).toBeVisible();

    await page.getByRole("link", { name: /Open competency lab/ }).click();
    await expect(page).toHaveURL(/\/train(?:\?|$)/);
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });

    // Give late async logs a moment to flush, then assert a clean console.
    await page.waitForTimeout(500);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
