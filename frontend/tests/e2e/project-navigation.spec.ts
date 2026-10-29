// PW-8 keyboard-only flow against the real API and PostgreSQL.
import { expect, test } from "@playwright/test";
import { blockExternal, tabTo, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));

test("PW-8: keyboard-only create, open and Sources/Reconstruction/Explore navigation", async ({ page }) => {
  const name = unique("Keyboard");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  await tabTo(page, page.getByLabel("Name"));
  await page.keyboard.type(name);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Description (optional)")).toBeFocused();
  await page.keyboard.type("created by keyboard");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Create project" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: `Saved “${name}”.` })).toBeVisible();

  await tabTo(page, page.getByRole("button", { name: `Open project ${name}` }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name })).toBeVisible();

  const nav = page.getByRole("navigation", { name: "Project sections" });
  await expect(nav.getByRole("button", { name: "Sources" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(/no source files/i)).toBeVisible();

  await tabTo(page, nav.getByRole("button", { name: "Reconstruction" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(/requires an imported source revision/i)).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(nav.getByRole("button", { name: "Explore" })).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByText(/requires a published model revision/i)).toBeVisible();
  await tabTo(page, nav.getByRole("button", { name: "Sources" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(/no source files/i)).toBeVisible();

  // No fake feature controls: only the real upload form (its submit stays disabled with no
  // selection) exists besides navigation and project editing. <button> elements only; the native
  // file input is a separate control.
  await expect(page.locator("button")).toHaveText([
    "Back to all projects",
    "Save changes",
    "Sources",
    "Reconstruction",
    "Explore",
    "Upload files",
  ]);
  await expect(page.getByRole("button", { name: "Upload files" })).toBeDisabled();

  await tabTo(page, page.getByRole("button", { name: "Back to all projects" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expect(page.getByRole("button", { name: `Open project ${name}` })).toBeVisible();
});
