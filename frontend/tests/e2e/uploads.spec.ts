// FL-005-A UI acceptance (implementer evidence, not independent acceptance). Real FastAPI +
// PostgreSQL + blob storage in a fresh database per run; only the abort test holds one request in
// the browser so the abort button can be exercised deterministically.
import { expect, test, type Page } from "@playwright/test";
import { blockExternal, createProject, projectId, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));

const csvBytes = (tag: string) => Buffer.from(`well_id,md_m,tvd_m\n${tag}-1,0,0\n${tag}-1,100,99.5\n`);
const notesBytes = (tag: string) => Buffer.from(`Field notes ${tag}\nNothing structured here.\n`);

async function openProject(page: Page, name: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" }).or(page.getByRole("heading", { name }))).toBeVisible();
  const open = page.getByRole("button", { name: `Open project ${name}` });
  if (await open.isVisible()) await open.click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

const filesTable = (page: Page) => page.getByRole("table", { name: "Files in this source revision" });

/** Fails loudly if any body row lacks its "Edit labels" action (so a row cannot silently drop out of files()). */
async function expectEveryBodyRowIsAFile(page: Page) {
  const bodyRows = filesTable(page).getByRole("rowgroup").last().getByRole("row");
  await expect(files(page)).toHaveCount(await bodyRows.count());
}

// One table row per file: the rows that carry the file's own "Edit labels" action.
const files = (page: Page) =>
  page
    .getByRole("table", { name: "Files in this source revision" })
    .getByRole("row")
    .filter({ has: page.getByRole("button", { name: /^Edit labels for/ }) });

test("UP-1: upload a CSV and an unknown text file, see honest statuses, dedupe, 415, abort and replay", async ({
  page,
}) => {
  const name = unique("Upload");
  const tag = unique("t");
  await page.goto("/");
  await createProject(page, name, "upload e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText(/no source files yet/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Upload source files" })).toBeVisible();
  const id = await projectId(page, name);

  // 1. Upload the CSV (with a category hint) and an unknown plain-text file.
  await page.getByLabel("Choose files").setInputFiles([
    { name: "wells.csv", mimeType: "text/csv", buffer: csvBytes(tag) },
    { name: "notes.txt", mimeType: "text/plain", buffer: notesBytes(tag) },
  ]);
  await page.getByLabel(/Category hint for wells\.csv/).selectOption("trajectory");
  await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Import accepted: 2 new file/ })).toBeVisible();

  // 2. Statuses are exactly what the API reports; nothing claims extraction.
  await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });
  await expect(files(page)).toHaveCount(2);
  await expectEveryBodyRowIsAFile(page);
  const csv = files(page).filter({ hasText: "wells.csv" });
  const txt = files(page).filter({ hasText: "notes.txt" });
  await expect(csv.getByText("Stored (hash-verified)")).toBeVisible();
  await expect(csv.getByText("Unsupported (no reader; not extracted)")).toBeVisible(); // settled text; the stale one-shot "Pending extraction" check raced the extraction worker (authorized correction)
  await expect(csv.locator("code")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(csv.getByText("Trajectory", { exact: false }).first()).toBeVisible();
  await expect(txt.getByText("Unsupported (no reader; not extracted)")).toBeVisible();
  await expect(page.getByText(/Extraction performed: no/)).toBeVisible();
  await expect(page.getByText(/extracted successfully/i)).toHaveCount(0);

  // 3. Re-uploading identical content is a no-op, reported as such.
  await page.getByLabel("Choose files").setInputFiles([
    { name: "wells.csv", mimeType: "text/csv", buffer: csvBytes(tag) },
    { name: "notes.txt", mimeType: "text/plain", buffer: notesBytes(tag) },
  ]);
  await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: /already belongs to the current source revision/ })).toBeVisible();

  // 4. A binary/executable is rejected with a visible 415 message; nothing is imported.
  const revisionsBefore = (await (await page.request.get(`/api/v1/projects/${id}/source-revisions`)).json()) as {
    items: unknown[];
  };
  await page.getByLabel("Choose files").setInputFiles([
    { name: "tool.bin", mimeType: "application/octet-stream", buffer: Buffer.concat([Buffer.from([0x7f, 0x45, 0x4c, 0x46]), Buffer.alloc(64)]) },
  ]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  // IN-10: the refusal names the file (red row with text) and says nothing was stored.
  await expect(page.getByRole("alert").filter({ hasText: /nothing was stored/i })).toBeVisible();
  await expect(page.getByRole("list", { name: "Selected files" }).getByText(/Refused:/)).toBeVisible();
  await page.getByRole("button", { name: "Remove tool.bin" }).click();

  // 5. Abort: hold the request in the browser, abort, and confirm the server saw no new revision.
  const held: { release: (() => void) | null } = { release: null };
  await page.route(`**/api/v1/projects/${id}/imports`, (route) => {
    held.release = () => void route.abort().catch(() => undefined);
  });
  await page.getByLabel("Choose files").setInputFiles([
    { name: "later.csv", mimeType: "text/csv", buffer: csvBytes(`${tag}-later`) },
  ]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByRole("progressbar", { name: "Upload progress" })).toBeVisible();
  await page.getByRole("button", { name: "Abort upload" }).click();
  const abortAlert = page.getByRole("alert").filter({ hasText: /nothing was imported/i });
  await expect(abortAlert).toBeVisible();
  await expect(abortAlert).toBeFocused();
  held.release?.();
  await page.unroute(`**/api/v1/projects/${id}/imports`);
  const revisionsAfter = (await (await page.request.get(`/api/v1/projects/${id}/source-revisions`)).json()) as {
    items: unknown[];
  };
  expect(revisionsAfter.items.length).toBe(revisionsBefore.items.length);
  await page.getByRole("button", { name: "Remove later.csv" }).click();

  // 6. Idempotent replay (HTTP 200) with the same key and request body.
  const session = (await (await page.request.get("/api/v1/session")).json()) as { csrf_token: string };
  const latest = (await (await page.request.get(`/api/v1/projects/${id}`)).json()) as {
    latest_source_revision_id: string;
  };
  const send = () =>
    page.request.post(`/api/v1/projects/${id}/imports`, {
      headers: { "x-fieldlens-token": session.csrf_token },
      multipart: {
        metadata: JSON.stringify({
          expected_parent_source_revision_id: latest.latest_source_revision_id,
          idempotency_key: `e2e-replay-${tag.replace(/\W/g, "")}`,
          files: [{ categories: [], tags: [], replaces_document_id: null }],
        }),
        files: { name: "replay.csv", mimeType: "text/csv", buffer: csvBytes(`${tag}-replay`) },
      },
    });
  const first = await send();
  expect(first.status(), await first.text()).toBe(202);
  const second = await send();
  expect(second.status()).toBe(200);
  expect(((await second.json()) as { replayed: boolean }).replayed).toBe(true);

  // 7. The UI shows the new revision after a reload; the earlier one is marked superseded.
  await openProject(page, name);
  await expect(page.getByText("(superseded)", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("row", { name: /\(latest\)/ })).toHaveCount(1);
});

test("UP-2: classification edit is keyboard operable and persists", async ({ page }) => {
  const name = unique("Labels");
  await page.goto("/");
  await createProject(page, name, "labels e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page.getByLabel("Choose files").setInputFiles([
    { name: "perfs.csv", mimeType: "text/csv", buffer: csvBytes(unique("p")) },
  ]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });

  const edit = page.getByRole("button", { name: "Edit labels for perfs.csv" });
  await edit.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("form", { name: "Edit labels for perfs.csv" }).locator(":focus")).toHaveCount(1);
  await page.getByLabel("Well logs").check();
  await page.getByLabel("Tags (comma separated)").fill("pilot, review");
  await page.getByRole("button", { name: "Save labels" }).click();
  await expect(edit).toBeFocused();
  await page.reload();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expectEveryBodyRowIsAFile(page);
  const row = files(page).filter({ hasText: "perfs.csv" });
  await expect(row.getByText(/Well logs/)).toBeVisible();
  await expect(row.getByText(/pilot, review/)).toBeVisible();
  await expect(row.getByText(/set by you/)).toBeVisible();
});

test("UP-3: 320px viewport never scrolls the page; the revisions region scrolls from the keyboard", async ({ page }) => {
  const name = unique("Narrow");
  await page.goto("/");
  await createProject(page, name, "narrow e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page.getByLabel("Choose files").setInputFiles([
    { name: "seed.csv", mimeType: "text/csv", buffer: csvBytes(unique("n")) },
  ]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });

  await page.setViewportSize({ width: 320, height: 640 });
  await page.getByLabel("Choose files").setInputFiles([
    { name: "a-rather-long-file-name-for-narrow-viewports.csv", mimeType: "text/csv", buffer: csvBytes(unique("m")) },
  ]);
  await expect(page.getByRole("button", { name: /^Remove a-rather-long/ })).toBeVisible();
  const dims = () =>
    page.locator("html").evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
  const page320 = await dims();
  expect(page320.client).toBe(320);
  expect(page320.scroll).toBeLessThanOrEqual(page320.client);

  const region = page.getByRole("region", { name: "Source revisions table" });
  const metrics = await region.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
  expect(metrics.sw).toBeGreaterThan(metrics.cw);
  await region.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => region.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
  const after = await dims();
  expect(after.scroll).toBeLessThanOrEqual(after.client);
});
