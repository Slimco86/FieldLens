// Real FastAPI + PostgreSQL (fresh database per run). Nothing here fakes persistence.
import { expect, test } from "@playwright/test";
import { blockExternal, createProject, projectId, restartApi, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));

test("PW-1: two empty projects persist across reload and a real API restart", async ({ page }) => {
  const a = unique("Alpha");
  const b = unique("Beta");
  const descA = `notes for ${a}`;
  const descB = `notes for ${b}`;
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await createProject(page, a, descA);
  await createProject(page, b, descB);

  // Edit A, then verify that the stored value (not browser state) changed.
  await page.getByRole("button", { name: `Open project ${a}` }).click();
  await expect(page.getByRole("heading", { name: a })).toBeVisible();
  await page.getByRole("button", { name: "Edit project details" }).click();
  const editedA = `${descA} (edited)`;
  await page.getByLabel("Description (optional)").fill(editedA);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Saved “${a}”.` })).toBeVisible();
  await expect(page.locator("dd", { hasText: editedA })).toBeVisible();

  // Reload: the selected existing project reopens by its persisted ID.
  await page.reload();
  await expect(page.getByRole("heading", { name: a })).toBeVisible();
  await expect(page.locator("dd", { hasText: editedA })).toBeVisible();

  await restartApi();

  for (const [name, description] of [[a, editedA], [b, descB]] as const) {
    await page.goto("/");
    const back = page.getByRole("button", { name: "Back to all projects" });
    await expect(back.or(page.getByRole("heading", { name: "Projects" }))).toBeVisible();
    if (await back.isVisible()) await back.click(); // a saved selection reopens its project
    await page.getByRole("button", { name: `Open project ${name}` }).click();
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await expect(page.locator("dd", { hasText: description })).toBeVisible();
    // Empty project: real pointers are null; no fabricated assets. The upload form exists but is idle.
    await expect(page.getByText("None yet")).toHaveCount(2);
    await expect(page.getByText(/no source files/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /upload/i })).toBeDisabled();
    await page.getByRole("button", { name: "Back to all projects" }).click();
  }
});

test("a restarted API refuses the old session token; retry succeeds and nothing was lost", async ({ page }) => {
  const name = unique("Gamma");
  await page.goto("/");
  await createProject(page, name, "before");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page.getByRole("button", { name: "Edit project details" }).click();
  await restartApi();
  await page.getByLabel("Description (optional)").fill("after");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("alert")).toContainText(/nothing was saved/i);
  await expect(page.locator("dd", { hasText: "before" })).toBeVisible(); // stored value still shown
  await expect(page.getByLabel("Description (optional)")).toHaveValue("after"); // entry retained
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await expect(page.locator("dd", { hasText: "after" })).toBeVisible();
});

test("PW-8: a missing saved project returns to the list with an explanation", async ({ page }) => {
  const name = unique("Delta");
  await page.goto("/");
  await createProject(page, name, "kept");
  const missing = "00000000-0000-4000-8000-000000000000";
  await page.evaluate(`window.localStorage.setItem("fieldlens.selectedProjectId", "${missing}")`);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expect(page.getByText(`The previously open project (${missing}) was not found`)).toBeVisible();
  await expect(page.getByRole("button", { name: `Open project ${name}` })).toBeVisible();
  expect(await page.evaluate(`window.localStorage.getItem("fieldlens.selectedProjectId")`)).toBeNull();
});

test("PW-8: switching during a delayed A response shows no A content or A actions under B", async ({ page }) => {
  const a = unique("Slow-A");
  const b = unique("Quick-B");
  const descA = `secret-A-${Date.now()}`;
  await page.goto("/");
  await createProject(page, a, descA);
  await createProject(page, b, "plain B");
  const idA = await projectId(page, a);

  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/v1/projects/${idA}`, async (route) => {
    await gate;
    await route.continue().catch(() => undefined); // the page may already have aborted it
  });

  await page.getByRole("button", { name: `Open project ${a}` }).click();
  await expect(page.getByText("Loading project…")).toBeVisible();
  await page.getByRole("button", { name: "Back to all projects" }).click();
  await page.getByRole("button", { name: `Open project ${b}` }).click();
  await expect(page.getByRole("heading", { name: b })).toBeVisible();
  release();
  await page.waitForTimeout(300);

  await expect(page.getByRole("heading", { name: b })).toBeVisible();
  await page.getByRole("button", { name: "Edit project details" }).click();
  await expect(page.getByLabel("Name")).toHaveValue(b);
  await expect(page.getByText(descA)).toHaveCount(0);
  // The sidebar lists every project by name; A must not appear anywhere in the project region.
  await expect(page.getByRole("main").getByText(a)).toHaveCount(0);
  expect(await page.evaluate(`window.localStorage.getItem("fieldlens.selectedProjectId")`)).not.toBe(idA);
  await page.reload();
  await expect(page.getByRole("heading", { name: b })).toBeVisible();
});

test("PW-8: a delayed save acknowledgement for A is rejected after switching to B", async ({ page }) => {
  const a = unique("Save-A");
  const b = unique("Save-B");
  await page.goto("/");
  await createProject(page, a, "orig");
  await createProject(page, b, "plain B");

  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/projects/*", async (route) => {
    if (route.request().method() === "PATCH") await gate;
    await route.continue().catch(() => undefined);
  });
  await page.getByRole("button", { name: `Open project ${a}` }).click();
  await expect(page.getByRole("heading", { name: a })).toBeVisible();
  await page.getByRole("button", { name: "Edit project details" }).click();
  await page.getByLabel("Description (optional)").fill("changed in A");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("button", { name: "Saving…" })).toBeVisible();
  await page.getByRole("button", { name: "Back to all projects" }).click();
  await page.getByRole("button", { name: `Open project ${b}` }).click();
  await expect(page.getByRole("heading", { name: b })).toBeVisible();
  release();
  await page.waitForTimeout(300);
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toHaveCount(0);
  await expect(page.getByRole("main").getByText(a)).toHaveCount(0);
  await page.getByRole("button", { name: "Edit project details" }).click(); // editor state was reset by the switch
  await expect(page.getByLabel("Name")).toHaveValue(b);
});
