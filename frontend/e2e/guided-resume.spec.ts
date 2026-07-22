import { expect, test } from "@playwright/test";


test("Guided hub resumes the newest actual scene instead of scene-list order", async ({ page }) => {
  const user = {
    userId: "u_guided_resume",
    username: "guided_resume",
    displayName: "Guided Learner",
    accountStatus: "verified",
    emailVerified: true,
  };
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({
    json: { authenticated: true, user },
  }));

  const productionItems = [
    {
      pathwayId: "production-curriculum",
      moduleId: "leads-vectors",
      sceneId: "M02.S10",
      status: "attempted",
      activeInteractionIndex: 1,
      completedActionIds: [],
      state: {},
      createdAt: "2026-07-14T08:00:00Z",
      updatedAt: "2026-07-14T08:00:00Z",
    },
    {
      pathwayId: "production-curriculum",
      moduleId: "leads-vectors",
      sceneId: "M02.S2",
      status: "viewed",
      activeInteractionIndex: 0,
      completedActionIds: [],
      state: {},
      createdAt: "2026-07-14T09:00:00Z",
      updatedAt: "2026-07-14T11:00:00Z",
    },
    {
      pathwayId: "production-curriculum",
      moduleId: "leads-vectors",
      sceneId: "M02.S3",
      status: "skipped",
      activeInteractionIndex: 0,
      completedActionIds: [],
      state: {},
      createdAt: "2026-07-14T10:00:00Z",
      updatedAt: "2026-07-14T12:00:00Z",
    },
    {
      pathwayId: "production-curriculum",
      moduleId: "leads-vectors",
      sceneId: "M02.S4",
      status: "complete",
      activeInteractionIndex: 0,
      completedActionIds: [],
      state: {},
      createdAt: "2026-07-14T10:00:00Z",
      updatedAt: "2026-07-14T13:00:00Z",
    },
  ];

  await page.route("**/api/backend/learning/resume", (route) => route.fulfill({
    json: {
      version: "learning-resume-v1",
      generatedAt: "2026-07-14T14:00:00Z",
      primary: {
        mode: "guided",
        phase: "in_progress",
        completed: 1,
        total: 15,
        updatedAt: "2026-07-14T11:00:00Z",
        destination: { kind: "guided", moduleId: "leads-vectors", sceneId: "M02.S2" },
      },
      additional: [],
    },
  }));
  await page.route("**/api/backend/learners/*/pathway-progress**", (route) => {
    const pathwayId = new URL(route.request().url()).searchParams.get("pathwayId");
    return route.fulfill({
      json: { learnerId: user.userId, items: pathwayId === "production-curriculum" ? productionItems : [] },
    });
  });

  await page.goto("/learn");

  await expect(page.getByRole("link", { name: "Resume Guided learning" })).toHaveAttribute(
    "href",
    "/learn/leads-vectors?scene=M02.S2",
  );
  await page.getByRole("button", { name: /Leads, Vectors, Axis/ }).click();
  await expect(page.getByRole("link", { name: "Resume pathway" })).toHaveAttribute(
    "href",
    "/learn/leads-vectors?scene=M02.S2",
  );
});


test("Guided resume accepts only an authored Foundations S0-S12 deep link", async ({ page }) => {
  const user = {
    userId: "u_foundations_resume",
    username: "foundations_resume",
    displayName: "Foundations Learner",
    accountStatus: "verified",
    emailVerified: true,
  };
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({
    json: { authenticated: true, user },
  }));
  await page.route("**/api/backend/learning/resume", (route) => route.fulfill({
    json: {
      version: "learning-resume-v1",
      generatedAt: "2026-07-19T14:00:00Z",
      primary: {
        mode: "guided",
        phase: "in_progress",
        completed: 11,
        total: 13,
        updatedAt: "2026-07-19T13:00:00Z",
        destination: { kind: "guided", moduleId: "foundations", sceneId: "S12" },
      },
      additional: [],
    },
  }));
  await page.route("**/api/backend/learners/*/pathway-progress**", (route) => route.fulfill({
    json: { learnerId: user.userId, items: [] },
  }));

  await page.goto("/learn");

  await expect(page.getByRole("link", { name: "Resume Guided learning" })).toHaveAttribute(
    "href",
    "/learn/foundations?scene=S12",
  );
});
