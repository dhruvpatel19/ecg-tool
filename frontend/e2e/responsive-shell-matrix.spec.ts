import { expect, test } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

const VIEWPORTS = [
  { name: "320px", width: 320, height: 700 },
  { name: "375px", width: 375, height: 812 },
  { name: "430px", width: 430, height: 932 },
] as const;

const PRIVATE_ROUTES = [
  { name: "Today", path: "/dashboard" },
  { name: "Guided", path: "/learn" },
  { name: "Focused", path: "/train" },
  { name: "Rapid", path: "/rapid" },
  { name: "Clinical", path: "/practice" },
  { name: "My learning", path: "/profile?tab=plan" },
  { name: "Account", path: "/account" },
] as const;

const PUBLIC_ROUTES = [
  { name: "Landing", path: "/" },
  { name: "Sign in", path: "/login" },
] as const;

test.describe("small-screen student shell", () => {
  test("shows labeled primary destinations and comfortable shell targets at 320px", async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "responsive_shell" });
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto("/dashboard");
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    for (const name of ["Today", "Guided learning", "Focused practice", "Rapid practice", "Clinical cases", "My learning"]) {
      await expect(navigation.getByRole("link", { name })).toBeVisible();
    }
    for (const label of ["Today", "Learn", "Train", "Rapid", "Cases", "Progress"]) {
      await expect(navigation.getByText(label, { exact: true })).toBeVisible();
    }

    const targets = await page.locator(".side-nav .brand, .side-nav .nav-link, .side-nav .nav-account-action").evaluateAll((elements) =>
      elements
        .filter((element) => {
          const style = window.getComputedStyle(element);
          const box = element.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
        })
        .map((element) => {
          const box = element.getBoundingClientRect();
          return { label: element.getAttribute("aria-label") ?? element.textContent?.trim(), width: box.width, height: box.height, right: box.right };
        }),
    );
    expect(targets.length).toBeGreaterThanOrEqual(8);
    expect(targets.every((target) => target.height >= 44 && target.right <= 321)).toBeTruthy();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("keeps ECG toolbar actions at the 44px touch comfort target on a phone", async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "responsive_toolbar" });
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto("/learn/leads-vectors?scene=M02.S1");
    await expect(page.getByRole("button", { name: "Zoom in" })).toBeVisible({ timeout: 30_000 });
    const sizes = await page.locator(".viewer-toolbar .icon-button").evaluateAll((elements) => elements.map((element) => {
      const box = element.getBoundingClientRect();
      return { width: box.width, height: box.height };
    }));
    expect(sizes.length).toBeGreaterThan(0);
    expect(sizes.every(({ width, height }) => width >= 44 && height >= 44)).toBeTruthy();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  for (const viewport of VIEWPORTS) {
    for (const route of PRIVATE_ROUTES) {
      test(`${route.name} reflows at ${viewport.name} without clipped controls`, async ({ page }) => {
        await registerVerifiedE2ELearner(page, { prefix: "responsive_matrix" });
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(route.path);
        await expect(page.getByRole("main")).toBeVisible();
        await page.waitForTimeout(350);

        const result = await page.evaluate(() => {
          const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
          const undersized = Array.from(document.querySelectorAll<HTMLElement>(
            'main button, main input, main select, main textarea, main summary, main [role="tab"]',
          )).filter((element) => {
            const style = window.getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return style.visibility !== "hidden"
              && style.display !== "none"
              && box.width > 0
              && box.height > 0
              && (box.width < 24 || box.height < 24);
          }).map((element) => ({
            tag: element.tagName.toLowerCase(),
            text: (element.innerText || element.getAttribute("aria-label") || "").trim().slice(0, 60),
            width: Math.round(element.getBoundingClientRect().width),
            height: Math.round(element.getBoundingClientRect().height),
          }));
          return { overflow, undersized };
        });

        expect(result.overflow, `Horizontal overflow on ${route.path} at ${viewport.name}`).toBeLessThanOrEqual(1);
        expect(result.undersized, `Controls below the WCAG 2.2 24px target minimum on ${route.path}`).toEqual([]);
      });
    }

    for (const route of PUBLIC_ROUTES) {
      test(`${route.name} reflows at ${viewport.name} without clipped controls`, async ({ page }) => {
        await page.route("**/api/backend/auth/me", (request) => request.fulfill({ json: { authenticated: false, user: null } }));
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(route.path);
        await expect(page.getByRole("main")).toBeVisible();
        await page.waitForTimeout(350);

        const result = await page.evaluate(() => {
          const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
          const undersized = Array.from(document.querySelectorAll<HTMLElement>(
            'main button, main input, main select, main textarea, main summary, main [role="tab"]',
          )).filter((element) => {
            const style = window.getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return style.visibility !== "hidden"
              && style.display !== "none"
              && box.width > 0
              && box.height > 0
              && (box.width < 24 || box.height < 24);
          }).map((element) => ({
            tag: element.tagName.toLowerCase(),
            text: (element.innerText || element.getAttribute("aria-label") || "").trim().slice(0, 60),
            width: Math.round(element.getBoundingClientRect().width),
            height: Math.round(element.getBoundingClientRect().height),
          }));
          return { overflow, undersized };
        });

        expect(result.overflow, `Horizontal overflow on ${route.path} at ${viewport.name}`).toBeLessThanOrEqual(1);
        expect(result.undersized, `Controls below the WCAG 2.2 24px target minimum on ${route.path}`).toEqual([]);
      });
    }
  }
});
