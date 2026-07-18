import { expect, test, type Page } from "@playwright/test";

type LoadingGeometry = {
  documentOverflow: number;
  navigationWidth: number;
  loadingLeft: number;
  loadingRight: number;
  loadingTop: number;
  loadingBottom: number;
  mainContentLeft: number;
  mainContentRight: number;
  viewportHeight: number;
};

async function openHydratedPublicShell(page: Page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator('[data-route-accessibility-ready="true"]')).toHaveText("ECG learning home loaded");
}

async function installPrivateRouteLoadingFixture(page: Page, learningRoute?: "rapid" | "cases") {
  await page.locator(".app-shell").evaluate((shell, route) => {
    shell.classList.remove("public-shell");
    shell.querySelector(".public-nav")?.remove();
    shell.querySelector(".side-nav")?.remove();
    const navigation = document.createElement("aside");
    navigation.className = `side-nav${route ? " learning-route-nav" : ""}`;
    if (route) navigation.dataset.learningRoute = route;
    navigation.setAttribute("aria-label", "Test navigation shell");
    shell.prepend(navigation);

    const main = shell.querySelector<HTMLElement>("#main-content")!;
    const section = document.createElement("section");
    section.className = "system-page system-page-loading";
    section.setAttribute("aria-labelledby", "route-loading-title");
    section.setAttribute("aria-busy", "true");
    section.innerHTML = `
      <span class="system-page-spinner" aria-hidden="true"></span>
      <div>
        <p class="eyebrow">Your learning workspace</p>
        <h1 id="route-loading-title">Preparing your workspace…</h1>
        <p>Loading your learning record and next activity.</p>
      </div>
    `;
    main.replaceChildren(section);
  }, learningRoute);
}

async function loadingGeometry(page: Page): Promise<LoadingGeometry> {
  return page.evaluate(() => {
    const main = document.querySelector<HTMLElement>("#main-content")!;
    const navigation = document.querySelector<HTMLElement>(".side-nav")!;
    const loading = document.querySelector<HTMLElement>(".system-page-loading")!;
    const mainBox = main.getBoundingClientRect();
    const loadingBox = loading.getBoundingClientRect();
    const mainStyle = getComputedStyle(main);
    return {
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      navigationWidth: navigation.getBoundingClientRect().width,
      loadingLeft: loadingBox.left,
      loadingRight: loadingBox.right,
      loadingTop: loadingBox.top,
      loadingBottom: loadingBox.bottom,
      mainContentLeft: mainBox.left + Number.parseFloat(mainStyle.paddingLeft),
      mainContentRight: mainBox.right - Number.parseFloat(mainStyle.paddingRight),
      viewportHeight: window.innerHeight,
    };
  });
}

test.describe("route loading shell", () => {
  test("centers the private loading state inside the desktop and mobile shell", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openHydratedPublicShell(page);
    await installPrivateRouteLoadingFixture(page);

    const desktop = await loadingGeometry(page);
    expect(desktop.documentOverflow).toBeLessThanOrEqual(1);
    expect(desktop.loadingLeft).toBeGreaterThanOrEqual(desktop.mainContentLeft - 1);
    expect(desktop.loadingRight).toBeLessThanOrEqual(desktop.mainContentRight + 1);
    expect(desktop.loadingTop).toBeGreaterThan(30);
    expect(desktop.loadingBottom).toBeLessThan(desktop.viewportHeight);

    await page.setViewportSize({ width: 320, height: 700 });
    // The fixture replaces a hydrated route tree. Reinstall it after the
    // responsive rerender so this assertion measures loading CSS, not the
    // marketing page React restores for the new viewport.
    await installPrivateRouteLoadingFixture(page);
    const mobile = await loadingGeometry(page);
    expect(mobile.documentOverflow).toBeLessThanOrEqual(1);
    expect(mobile.loadingLeft).toBeGreaterThanOrEqual(mobile.mainContentLeft - 1);
    expect(mobile.loadingRight).toBeLessThanOrEqual(mobile.mainContentRight + 1);
    expect(mobile.loadingTop).toBeGreaterThanOrEqual(102);
    expect(mobile.loadingBottom).toBeLessThanOrEqual(mobile.viewportHeight);
  });

  test("uses the compact learning rail before Rapid and Clinical route content mounts", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openHydratedPublicShell(page);

    for (const route of ["rapid", "cases"] as const) {
      await installPrivateRouteLoadingFixture(page, route);
      const loading = await loadingGeometry(page);
      expect(loading.navigationWidth).toBeGreaterThanOrEqual(75);
      expect(loading.navigationWidth).toBeLessThanOrEqual(77);

      await page.locator("#main-content").evaluate((main, mode) => {
        const mounted = document.createElement("div");
        mounted.className = mode === "rapid" ? "rapid-page" : "clinical-shell";
        main.replaceChildren(mounted);
      }, route);
      const mountedWidth = await page.locator(".side-nav").evaluate((navigation) => navigation.getBoundingClientRect().width);
      expect(Math.abs(mountedWidth - loading.navigationWidth)).toBeLessThanOrEqual(1);
    }
  });
});
