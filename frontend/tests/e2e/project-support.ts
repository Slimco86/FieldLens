import { expect, type Locator, type Page } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execute = promisify(execFile);

/** Real process restart of the API (same PostgreSQL database) through the runner. */
export async function restartApi() {
  await execute("uv", ["run", "--project", "..", "python", "../scripts/run_e2e.py", "--api-restart"]);
}

export async function blockExternal(page: Page) {
  await page.route("**/*", async (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host !== "127.0.0.1" && host !== "localhost") return route.abort("blockedbyclient");
    return route.continue();
  });
}

export const unique = (label: string) => `${label} ${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export async function createProject(page: Page, name: string, description: string) {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Description (optional)").fill(description);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Saved “${name}”.` })).toBeVisible();
  await expect(page.getByRole("button", { name: `Open project ${name}` })).toBeVisible();
}

export async function projectId(page: Page, name: string): Promise<string> {
  const res = await page.request.get("/api/v1/projects?limit=200");
  const body = (await res.json()) as { items: { project_id: string; name: string }[] };
  const found = body.items.find((p) => p.name === name);
  if (!found) throw new Error(`project ${name} not found`);
  return found.project_id;
}

/** Keyboard-only focus movement: Tab (then Shift+Tab) until the target holds focus. */
export async function tabTo(page: Page, target: Locator) {
  for (const key of ["Tab", "Shift+Tab"]) {
    for (let i = 0; i < 60; i += 1) {
      await page.keyboard.press(key);
      const focused = await target.evaluate(
        (el: { ownerDocument: { activeElement: unknown } }) => el === el.ownerDocument.activeElement,
      );
      if (focused) return;
    }
  }
  throw new Error("target never received keyboard focus");
}
