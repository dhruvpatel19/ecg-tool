import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const surfaces = [
  { path: "/privacy", heading: "Your learning record should help you—not surprise you.", title: "Privacy and learning data · TRACE" },
  { path: "/terms", heading: "Use TRACE for learning—not patient care.", title: "Terms of use · TRACE" },
  { path: "/accessibility", heading: "ECG learning should remain usable across abilities and devices.", title: "Accessibility · TRACE" },
  { path: "/data-sources", heading: "Real ECGs, versioned sources, visible limits.", title: "Data sources and attribution · TRACE" },
] as const;

test.describe("public trust and policy pages", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2_000));
      await route.fulfill({ json: { authenticated: false, user: null } });
    });
  });

  for (const surface of surfaces) {
    test(`${surface.path} renders without waiting for authentication and passes axe`, async ({ page }) => {
      await page.goto(surface.path);
      await expect(page.getByRole("heading", { name: surface.heading })).toBeVisible({ timeout: 1_500 });
      await expect(page).toHaveTitle(surface.title);
      await expect(page.getByRole("navigation", { name: "Website navigation" })).toBeVisible();
      await expect(page.locator(".side-nav")).toHaveCount(0);
      await expect(page.getByText(/continue as guest|guest learner|guest learning/i)).toHaveCount(0);

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations.map(({ id, impact }) => ({ id, impact }))).toEqual([]);
    });
  }

  test("the landing footer reaches every public trust page", async ({ page }) => {
    await page.goto("/");
    for (const [name, href] of [
      ["Privacy", "/privacy"],
      ["Terms", "/terms"],
      ["Accessibility", "/accessibility"],
      ["Data sources", "/data-sources"],
    ] as const) {
      await expect(page.getByRole("contentinfo").getByRole("link", { name })).toHaveAttribute("href", href);
    }
  });

  test("data attribution links target versioned official dataset records", async ({ page }) => {
    await page.goto("/data-sources");
    await expect(page.getByRole("link", { name: "Official PhysioNet record" })).toHaveCount(4);
    await expect(page.getByRole("link", { name: "Official PhysioNet record" }).first())
      .toHaveAttribute("href", "https://physionet.org/content/ptb-xl/1.0.3/");
  });
});
