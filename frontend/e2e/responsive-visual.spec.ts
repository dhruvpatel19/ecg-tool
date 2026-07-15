import { expect, test } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 },
];

test.describe("responsive production learning workspace", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "responsive_visual" });
  });

  for (const viewport of VIEWPORTS) {
    test(`${viewport.name} keeps the module, ECG, and tutor workspace inside the viewport`, async ({ page }) => {
      const errors = collectConsoleErrors(page);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto("/learn/leads-vectors?scene=M02.S1");
      const lessonHeading = page.getByRole("heading", { name: "Why does one beat look different twelve times?" });
      await expect(lessonHeading).toBeVisible({ timeout: 30_000 });

      if (viewport.name === "mobile") {
        const main = page.locator("#main-content");
        await expect(main).toBeFocused();
        const mainBox = await main.boundingBox();
        expect(mainBox).not.toBeNull();
        expect(mainBox!.y).toBeGreaterThanOrEqual(0);
        expect(mainBox!.y).toBeLessThan(viewport.height);
      }

      // These assertions may scroll the ECG metadata into view on a phone, so
      // validate the route-focus contract above before exercising the trace.
      await expect(page.getByText(/25 mm\/s/).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/10 mm\/mV/).first()).toBeVisible();

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      await page.screenshot({ path: `test-results/production-${viewport.name}.png`, fullPage: false });
      expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
    });
  }
});
