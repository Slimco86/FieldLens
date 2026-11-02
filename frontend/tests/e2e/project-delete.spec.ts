// Real FastAPI + PostgreSQL. TASK-071 AC-9: typed-name deletion through the real purge.
import { expect, test } from "@playwright/test";
import { blockExternal, createProject, projectId, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));

test("deleting a project needs the exact name, completes, and clears the selection", async ({ page }) => {
  const keep = unique("Keep");
  const doomed = unique("Doomed");
  await page.goto("/");
  await createProject(page, keep, "stays");
  await createProject(page, doomed, "goes");
  await page.getByRole("button", { name: `Open project ${doomed}` }).click();
  await expect(page.getByRole("heading", { name: doomed })).toBeVisible();
  const id = await projectId(page, doomed);

  await page.getByRole("button", { name: `Delete project ${doomed}` }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/cannot be undone/i)).toBeVisible();
  await expect(dialog.getByText("Documents", { exact: true })).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "Delete project" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/Type the project name/).fill(doomed.toLowerCase());
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/Type the project name/).fill(doomed);
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect(dialog).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: `Open project ${doomed}` })).toHaveCount(0);
  await expect(page.getByRole("button", { name: `Open project ${keep}` })).toBeVisible();
  expect((await page.request.get(`/api/v1/projects/${id}`)).status()).toBe(404);
  expect(await page.evaluate(() => window.localStorage.getItem("fieldlens.selectedProjectId"))).not.toBe(id);
});
