// TASK-009 UI acceptance (implementer evidence, not independent acceptance): upload a small
// synthetic LAS file and an unsupported text file through the real API, let the extraction worker
// run, then inspect profile, status, records with locators, data-quality findings and the
// empty/error states. Real FastAPI + PostgreSQL; only the error test fails one request in the browser.
import { expect, test, type Page } from "@playwright/test";
import { blockExternal, createProject, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));

const LAS = [
  "~VERSION INFORMATION",
  " VERS.   2.0 : CWLS LOG ASCII STANDARD - VERSION 2.0",
  " WRAP.   NO  : ONE LINE PER DEPTH STEP",
  "~WELL INFORMATION",
  " STRT.M   100.0 : START DEPTH",
  " STOP.M   102.0 : STOP DEPTH",
  " STEP.M   1.0 : STEP",
  " NULL.    -999.25 : NULL VALUE",
  " WELL.    15/9-F-99 : WELL (synthetic)",
  " DATE.    : LOG DATE",
  "~CURVE INFORMATION",
  " DEPT.M    : DEPTH",
  " GR  .GAPI : GAMMA",
  " RHOB.----   : DENSITY",
  "~A",
  " 100.0 50.0 2.40",
  " 101.0 -999.25 2.41",
  " 102.0 55.5 2.42",
  "",
].join("\n");

async function openWithUploads(page: Page, name: string) {
  await page.goto("/");
  await createProject(page, name, "evidence e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByLabel("Choose files").setInputFiles([
    { name: "synthetic.las", mimeType: "text/plain", buffer: Buffer.from(LAS) },
    { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("Field notes\nNothing structured.\n") },
  ]);
  await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Import accepted: 2 new file/ })).toBeVisible();
}

test("TASK-009: evidence panel shows profile, status, records with locators, findings and unsupported state", async ({
  page,
}) => {
  await openWithUploads(page, unique("Evidence"));

  // Supported file: detected by content, extracted with evidence.
  const las = page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ });
  await expect(las).toBeVisible({ timeout: 30_000 });
  await las.click();
  await expect(page.getByText(/las_2_0 v/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Succeeded|Partial/).first()).toBeVisible();
  const findings = page.getByRole("list", { name: "Data-quality findings" });
  await expect(findings).toBeVisible();
  await expect(findings.getByText(/MISSING_UNIT|MISSING_REFERENCE/).first()).toBeVisible();
  const records = page.getByRole("list", { name: /Extracted records for synthetic\.las/ });
  await expect(records).toBeVisible();
  await expect(records.getByText(/line \d+/).first()).toBeVisible();
  await expect(page.getByText(/completion string, packers and tubing are not extracted/)).toHaveCount(0);

  // Unsupported file: honest empty state, nothing extracted, no records claimed.
  await page.getByRole("button", { name: /Inspect extraction for notes\.txt/ }).click();
  await expect(page.getByText(/Unsupported \(no profile matches the content\)/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("none matched the file content")).toBeVisible();
});

test("TASK-009: a failed report request shows an alert and recovers on keyboard retry", async ({ page }) => {
  await openWithUploads(page, unique("EvidenceError"));
  const inspect = page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ });
  await expect(inspect).toBeVisible({ timeout: 30_000 });

  let failures = 1;
  const handler = async (route: import("@playwright/test").Route) => {
    if (failures > 0 && route.request().method() === "GET") {
      failures -= 1;
      return route.abort();
    }
    return route.continue();
  };
  await page.route(/\/documents\/[^/]+\/extraction$/, handler);
  await inspect.click();
  await expect(page.getByRole("alert").filter({ hasText: /could not be loaded/ })).toBeVisible();
  const retry = page.getByRole("button", { name: "Retry loading extraction report" });
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/las_2_0 v/).first()).toBeVisible({ timeout: 60_000 });
  await page.unroute(/\/documents\/[^/]+\/extraction$/, handler);
});
