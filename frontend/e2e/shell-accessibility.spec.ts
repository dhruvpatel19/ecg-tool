import { expect, test } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

test.describe("application shell", () => {
  test("server-renders a distinct title for each canonical learner workspace", async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "shell_titles" });
    const routes = [
      ["/", "TRACE · ECG learning for medical students"],
      ["/learn", "Guided learning · TRACE"],
      ["/train", "Focused practice · TRACE"],
      ["/rapid", "Rapid practice · TRACE"],
      ["/practice", "Clinical cases · TRACE"],
      ["/home", "Learning dashboard · TRACE"],
      ["/account", "Account · TRACE"],
      ["/login", "Sign in or create an account · TRACE"],
    ] as const;

    for (const [path, title] of routes) {
      const response = await page.request.get(path);
      expect(response.ok(), `${path} should render successfully`).toBe(true);
      expect(await response.text()).toContain(`<title>${title}</title>`);
    }
  });

  test("client navigation announces the route and moves focus to the single main region", async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "shell_navigation" });
    await page.goto("/home");
    await page.getByRole("link", { name: "Guided learning" }).click();

    await expect(page).toHaveURL(/\/learn$/);
    await expect(page.getByRole("main")).toBeFocused();
    await expect(page.getByText("Guided learning loaded", { exact: true })).toBeAttached();
    await expect(page).toHaveTitle("Guided learning · TRACE");
    await expect(page.getByRole("main")).toHaveCount(1);
  });

  test("unknown routes recover through a useful not-found page", async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "shell_not_found" });
    await page.goto("/this-route-does-not-exist");

    await expect(page.getByRole("heading", { name: "That learning route is not available." })).toBeVisible();
    await expect(page.getByRole("link", { name: "Return to dashboard" })).toHaveAttribute("href", "/home");
  });
});
