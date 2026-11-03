// Real FastAPI + PostgreSQL. TASK-071 AC-9: typed-name deletion through the real purge.
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { blockExternal, createProject, projectId, tabTo, unique } from "./project-support";

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

test("the delete icon sits on the name's line, truncates long names and stays keyboard reachable", async ({ page }) => {
  const long = unique(`Lengthy ${"segment ".repeat(11).trim()}`);
  await page.goto("/");
  await createProject(page, long, "layout");
  const open = page.getByRole("button", { name: `Open project ${long}` });
  const del = page.getByRole("button", { name: `Delete project ${long}` });
  for (const size of [{ width: 390, height: 844 }, { width: 1280, height: 800 }]) {
    await page.setViewportSize(size);
    const burger = page.getByRole("button", { name: "Toggle project sidebar" });
    if (size.width < 992 && (await burger.isVisible()) && !(await del.isVisible())) await burger.click();
    await expect(del).toBeVisible();
    const o = (await open.boundingBox())!;
    const d = (await del.boundingBox())!;
    const label = `${size.width}px`;
    expect(d.width, label).toBeGreaterThanOrEqual(24);
    expect(d.height, label).toBeGreaterThanOrEqual(24);
    expect(Math.abs(o.y + o.height / 2 - (d.y + d.height / 2)), `same line ${label}`).toBeLessThanOrEqual(o.height / 2);
    expect(o.x + o.width, `no overlap ${label}`).toBeLessThanOrEqual(d.x + 0.5);
    expect(d.x + d.width, `inside viewport ${label}`).toBeLessThanOrEqual(size.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `no h-overflow ${label}`).toBe(true);
  }
  await expect(open).toHaveAttribute("title", long);
  await tabTo(page, del);
  await expect(del).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(del).toBeFocused();
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
});
