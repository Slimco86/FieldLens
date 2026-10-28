import { expect, test } from "@playwright/test";

test("shell reports readiness and exposes no token in static output", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FieldLens" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Workspace" })).toBeVisible();
  const html = await page.content();
  expect(html).not.toMatch(/csrf_token|FIELDLENS_DB_PASSWORD/);
});
