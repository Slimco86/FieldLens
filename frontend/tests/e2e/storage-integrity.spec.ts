// TASK-070 AC-8 (UI). Real FastAPI + PostgreSQL for the upload and the file list; the Failed state
// and the retry endpoint are simulated at the browser boundary (page.route) because the product
// exposes no way to damage a stored copy. Backend behavior of retry/heal is proven by the backend tests.
import { expect, test } from "@playwright/test";
import { blockExternal, createProject, projectId, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));

test("AC-8: a Failed file shows the stated message, Retry restores it, no quarantine wording", async ({ page }) => {
  const name = unique("StorageIntegrity");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await createProject(page, name, "storage integrity e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  const id = await projectId(page, name);

  let failed = true;
  let retries = 0;
  await page.route(`**/api/v1/projects/${id}/documents?*`, async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as { items: Record<string, unknown>[] };
    if (failed) {
      for (const item of body.items) {
        item["storage_state"] = "failed";
        item["storage_failure_reason"] = "missing";
        item["storage_message"] = "Failed: stored copy missing or damaged.";
      }
    }
    await route.fulfill({ response: res, json: body });
  });
  await page.route(`**/api/v1/projects/${id}/documents/*/storage/retry`, async (route) => {
    retries += 1;
    failed = false;
    await route.fulfill({
      status: 200,
      json: {
        document_id: route.request().url().split("/documents/")[1]?.split("/")[0],
        outcome: "restored",
        storage_state: "stored",
        extraction_queued: true,
        message: "Restored: the stored copy verified and extraction was queued.",
      },
    });
  });

  await page.getByLabel("Choose files").setInputFiles([
    { name: "wells.csv", mimeType: "text/csv", buffer: Buffer.from("well_id,md_m,tvd_m\nA-1,0,0\nA-1,100,99.5\n") },
  ]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByText("Failed: stored copy missing or damaged.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("Choose files")).toBeVisible(); // the upload control is the re-upload route
  await expect(page.locator("body")).not.toContainText(/quarant/i);

  await expect(page.getByText("Not available: stored copy missing or damaged")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/verification_missing|Extracted with/);
  const msg = page.getByText("Failed: stored copy missing or damaged.");
  const clipped = await msg.evaluate((el) => el.scrollWidth > el.clientWidth + 1);
  expect(clipped, "Failed text wraps inside the Storage column at 1440px").toBe(false);
  const retry = page.getByRole("button", { name: /Retry storage verification for wells\.csv/ });
  await retry.focus();
  await expect(retry).toBeFocused();
  await retry.click();
  await expect(page.getByText(/Restored: the stored copy verified/)).toBeVisible();
  await expect(page.getByText("Failed: stored copy missing or damaged.")).toHaveCount(0);
  expect(retries).toBe(1);
});
