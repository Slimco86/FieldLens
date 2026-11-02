// TASK-034 shell acceptance (implementer evidence, not independent acceptance): URL routing (UI-12),
// unavailable-capability states (UI-6), zero external requests (UI-8), keyboard/focus/reduced motion
// (UI-9), large-screen layout (UI-2, screenshots for the UI-10 reviewer) and axe (UI-3) against the
// real API and PostgreSQL. Screenshots go to ../.local/screens/task-034 (gitignored).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { blockExternal, createProject, projectId, unique } from "./project-support";

const SHOTS = "../.local/screens/task-034";
mkdirSync(SHOTS, { recursive: true });

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

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectNoSeriousAxe(page: Page, label: string) {
  const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  expect(result.passes.length, `axe actually evaluated rules on ${label}`).toBeGreaterThan(15);
  const lesser = result.violations.filter((v) => v.impact !== "serious" && v.impact !== "critical");
  if (lesser.length > 0) console.log(`axe moderate/minor on ${label}: ${lesser.map((v) => `${v.id}(${v.impact})`).join(", ")}`);
  const bad = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    bad.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
    `axe serious/critical on ${label}`,
  ).toEqual([]);
}

async function noPageOverflow(page: Page) {
  const dims = await page.locator("html").evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
  expect(dims.scroll).toBeLessThanOrEqual(dims.client);
}

async function primaryControlsInside(page: Page) {
  const width = page.viewportSize()?.width ?? 0;
  const boxes = await page
    .locator("main button, main a, main input, aside button")
    .evaluateAll((els) =>
      els
        .filter((el) => (el as HTMLElement).offsetParent !== null || getComputedStyle(el).position === "fixed")
        .map((el) => {
          const r = el.getBoundingClientRect();
          return { left: r.left, right: r.right, w: r.width, name: el.textContent?.trim().slice(0, 30) ?? "" };
        }),
    );
  for (const b of boxes) {
    if (b.w === 0) continue;
    expect(b.left, `${b.name} left`).toBeGreaterThanOrEqual(0);
    expect(b.right, `${b.name} right`).toBeLessThanOrEqual(width + 1);
  }
}

async function apiProject(page: Page, name: string, description = "shell e2e") {
  const session = (await (await page.request.get("/api/v1/session")).json()) as { csrf_token: string };
  const res = await page.request.post("/api/v1/projects", {
    headers: { "x-fieldlens-token": session.csrf_token },
    data: { name, description },
  });
  return ((await res.json()) as { project_id: string }).project_id;
}

test("UI-8: the built app makes zero external requests and serves Inter locally", async ({ page }) => {
  const origin = new URL(test.info().project.use.baseURL ?? "http://127.0.0.1:8101").origin;
  const outside: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (!url.startsWith("data:") && !url.startsWith("blob:") && new URL(url).origin !== origin) outside.push(url);
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Workspace" })).toBeVisible();
  await createProject(page, unique("Net"), "network check");
  await page.getByRole("button", { name: /^Open project Net/ }).first().click();
  await page.getByRole("button", { name: "Reconstruction" }).click();
  await page.getByRole("button", { name: "Explore" }).click();
  expect(outside).toEqual([]);
  expect(await page.evaluate(() => document.fonts.check("14px 'Inter Variable'"))).toBe(true);
  const sources = await page.evaluate(() => performance.getEntriesByType("resource").map((e) => e.name));
  expect(sources.some((u) => /inter-.*\.woff2$/.test(u))).toBe(true);
});

test("UI-12/UI-6: URL selects project and tab; prerequisites come from revision pointers; no unsupported controls", async ({
  page,
}) => {
  await blockExternal(page);
  const name = unique("Route");
  const id = await apiProject(page, name);
  await page.goto(`/#/projects/${id}/reconstruction`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Project sections" });
  await expect(nav.getByRole("button", { name: "Reconstruction" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(/requires an imported source revision/i)).toBeVisible();

  await nav.getByRole("button", { name: "Explore" }).click();
  await expect(page).toHaveURL(new RegExp(`#/projects/${id}/explore$`));
  await expect(page.getByText(/requires a published model revision/i)).toBeVisible();
  await expect(page.getByRole("region", { name: "Stage" })).toBeVisible();
  for (const region of ["Tree", "Inspector", "Dock"]) {
    await expect(page.getByRole("region", { name: region })).toHaveCount(0); // empty regions render nothing
  }

  await page.goBack();
  await expect(nav.getByRole("button", { name: "Reconstruction" })).toHaveAttribute("aria-current", "page");
  await page.goForward();
  await expect(nav.getByRole("button", { name: "Explore" })).toHaveAttribute("aria-current", "page");
  await page.reload();
  await expect(nav.getByRole("button", { name: "Explore" })).toHaveAttribute("aria-current", "page");

  // No fake feature controls: nothing that removes, replaces or deletes a source or project.
  await nav.getByRole("button", { name: "Sources" }).click();
  await expect(page).toHaveURL(new RegExp(`#/projects/${id}/sources$`));
  // Scoped to <main>: the sidebar's intended "Delete project …" control (TASK-071) is not a per-source control.
  await expect(page.getByRole("main").getByRole("button", { name: /remove|replace|delete|archive/i })).toHaveCount(0);

  // Switching project by sidebar changes the URL and resets the tab to Sources.
  const other = unique("Other");
  const otherId = await apiProject(page, other);
  await page.reload();
  await nav.getByRole("button", { name: "Explore" }).click();
  await page.getByRole("button", { name: `Open project ${other}` }).click();
  await expect(page).toHaveURL(new RegExp(`#/projects/${otherId}/sources$`));
  await expect(page.getByRole("heading", { name: other })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Sources" })).toHaveAttribute("aria-current", "page");

  // A malformed project ID in the address is refused without any request for it.
  const seen: string[] = [];
  page.on("request", (r) => seen.push(r.url()));
  await page.goto("/#/projects/not-a-uuid/sources");
  await expect(page.getByText(/project ID in the address is not valid/i)).toBeVisible();
  expect(seen.some((u) => u.includes("not-a-uuid"))).toBe(false);
});

test("dropzone: files dropped on the zone are added to the selection like picked files", async ({ page }) => {
  await blockExternal(page);
  const name = unique("Drop");
  const id = await apiProject(page, name);
  await page.goto(`/#/projects/${id}/sources`);
  await expect(page.getByText(/no source files yet/i)).toBeVisible();
  const zone = page.getByText("Drop files here, or choose them with the file picker.").locator("..");
  const transfer = await page.evaluateHandle(() => {
    const dt = new DataTransfer();
    dt.items.add(new File(["a,b\n1,2\n"], "dropped.csv", { type: "text/csv" }));
    return dt;
  });
  await zone.dispatchEvent("dragenter", { dataTransfer: transfer });
  await zone.dispatchEvent("dragover", { dataTransfer: transfer });
  await zone.dispatchEvent("drop", { dataTransfer: transfer });
  await expect(page.getByLabel(/Category hint for dropped\.csv/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload 1 file(s)" })).toBeEnabled();
});

test("UI-9: skip link, landmarks, visible focus ring and reduced motion", async ({ page }) => {
  await blockExternal(page);
  const name = unique("Keys");
  const id = await apiProject(page, name);
  await page.goto(`/#/projects/${id}/sources`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  for (const role of ["banner", "complementary", "main", "navigation"] as const) {
    await expect(page.getByRole(role).first()).toBeVisible();
  }

  // The skip link moves focus to <main> and keeps the route (the hash is the route).
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await skip.focus();
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await expect(page).toHaveURL(new RegExp(`#/projects/${id}/sources$`));
  await page.evaluate(`window.localStorage.clear()`); // no saved selection to restore
  await page.goto("/#/");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await page.keyboard.press("Tab"); // first tab stop of a fresh page is the skip link
  await expect(skip).toBeFocused();

  await page.goto(`/#/projects/${id}/sources`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  // Every focused control shows a token-defined ring (2 px solid, brand color).
  const ring = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    return { width: root.getPropertyValue("--fl-focus-ring-width").trim(), color: root.getPropertyValue("--fl-color-focus-ring").trim() };
  });
  expect(ring.width).toBe("2px");
  const tab = page.getByRole("navigation", { name: "Project sections" }).getByRole("button", { name: "Sources" });
  await tab.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(tab).toBeFocused();
  const style = await tab.evaluate((el) => {
    const s = getComputedStyle(el);
    return { width: s.outlineWidth, style: s.outlineStyle, color: s.outlineColor };
  });
  expect(style.style).toBe("solid");
  expect(style.width).toBe(ring.width);
  const hex = ring.color.replace("#", "");
  const rgb = `rgb(${parseInt(hex.slice(0, 2), 16)}, ${parseInt(hex.slice(2, 4), 16)}, ${parseInt(hex.slice(4, 6), 16)})`;
  expect(style.color).toBe(rgb);

  // prefers-reduced-motion removes non-essential motion.
  await page.emulateMedia({ reducedMotion: "reduce" });
  const durations = await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.animation = "fl-probe 3s linear infinite";
    probe.style.transition = "opacity 2s";
    document.body.appendChild(probe);
    const s = getComputedStyle(probe);
    const out = { animation: parseFloat(s.animationDuration), transition: parseFloat(s.transitionDuration) };
    probe.remove();
    return out;
  });
  expect(durations.animation).toBeLessThan(0.01);
  expect(durations.transition).toBeLessThan(0.01);
  await page.emulateMedia({ reducedMotion: "no-preference" });
});

test("UI-3: axe finds no serious or critical issue in loaded, empty and error states", async ({ page }) => {
  await blockExternal(page);
  const name = unique("Axe");
  const id = await apiProject(page, name);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expectNoSeriousAxe(page, "home (loaded)");

  await page.goto(`/#/projects/${id}/sources`);
  await expect(page.getByText(/no source files yet/i)).toBeVisible();
  await expectNoSeriousAxe(page, "sources (empty)");
  await page.getByRole("button", { name: "Edit project details" }).click();
  await expectNoSeriousAxe(page, "sources (project editor open)");

  await page.getByLabel("Choose files").setInputFiles([
    { name: "synthetic.las", mimeType: "text/plain", buffer: Buffer.from(LAS) },
    { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("Field notes\nNothing structured.\n") },
  ]);
  await expectNoSeriousAxe(page, "sources (files selected)");
  await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
  await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ }).click();
  await expect(page.getByText(/las_2_0 v/).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Edit labels for notes.txt" }).click();
  await expectNoSeriousAxe(page, "sources (loaded, inspection and label editor open)");

  await page.getByRole("button", { name: "Reconstruction" }).click();
  await expectNoSeriousAxe(page, "reconstruction (unavailable)");
  await page.getByRole("button", { name: "Explore" }).click();
  await expectNoSeriousAxe(page, "explore (unavailable)");

  // Error state: the project request fails.
  await page.route(`**/api/v1/projects/${id}`, (route) => route.abort());
  await page.reload();
  await expect(page.getByRole("alert").filter({ hasText: /could not be loaded/ })).toBeVisible();
  await expectNoSeriousAxe(page, "project (error)");
  await page.unroute(`**/api/v1/projects/${id}`);

  // Services unavailable (readiness fails).
  await page.route("**/ready", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("The local API is unreachable.");
  await expectNoSeriousAxe(page, "services unavailable");
});

for (const size of [
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
]) {
  test(`UI-2/UI-10: large-screen layout without page scroll at ${size.width}x${size.height}`, async ({ page }) => {
    test.setTimeout(120_000);
    await blockExternal(page);
    await page.setViewportSize(size);
    const tag = `${size.width}x${size.height}`;
    const name = unique(`Screens ${tag}`);
    const id = await apiProject(page, name, "Shell review project: synthetic LAS and notes only.");
    await apiProject(page, unique("Second project"), "another project");

    const shot = async (view: string) => {
      await noPageOverflow(page);
      await primaryControlsInside(page);
      await page.screenshot({ path: `${SHOTS}/${view}-${tag}.png` });
    };

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await shot("home");

    await page.goto(`/#/projects/${id}/sources`);
    await expect(page.getByText(/no source files yet/i)).toBeVisible();
    await shot("sources-empty");

    await page.getByLabel("Choose files").setInputFiles([
      { name: "synthetic.las", mimeType: "text/plain", buffer: Buffer.from(LAS) },
      { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("Field notes\nNothing structured.\n") },
    ]);
    await shot("sources-selected");
    await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
    await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ })).toBeVisible();
    await shot("sources-loaded");

    await page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ }).click();
    await expect(page.getByText(/las_2_0 v/).first()).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Edit labels for notes.txt" }).click();
    await shot("sources-inspection");

    await page.getByRole("button", { name: "Reconstruction" }).click();
    await expect(page.getByText(/Reconstruction is not available in this build/)).toBeVisible();
    await shot("reconstruction");
    await page.getByRole("button", { name: "Explore" }).click();
    await expect(page.getByText(/requires a published model revision/i)).toBeVisible();
    await shot("explore");

    await page.route(`**/api/v1/projects/${id}`, (route) => route.abort());
    await page.reload();
    await expect(page.getByRole("alert").filter({ hasText: /could not be loaded/ })).toBeVisible();
    await shot("project-error");
    await page.unroute(`**/api/v1/projects/${id}`);
    expect(await projectId(page, name)).toBe(id);
  });
}

// Repair D1: the longest allowed (120 character) unbroken project name must not break any region.
const longName = () => `QA <b>bold</b> Ünïcode 油田 ${"L".repeat(120)}`.slice(0, 100) + Date.now().toString(36).padStart(20, "L").slice(-20);

for (const size of [
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
]) {
  test(`D1: a 120-character unbroken project name keeps every region inside its box at ${size.width}x${size.height}`, async ({
    page,
  }) => {
    await blockExternal(page);
    await page.setViewportSize(size);
    const LONG_NAME = longName();
    expect(LONG_NAME.length).toBe(120);
    const id = await apiProject(page, LONG_NAME, "long name check");
    await apiProject(page, unique("Neighbour"), "short");
    await page.goto(`/#/projects/${id}/sources`);
    await expect(page.getByRole("heading", { name: LONG_NAME })).toBeVisible();

    const sidebar = page.getByRole("complementary", { name: "Project sidebar" });
    const box = await sidebar.boundingBox();
    expect(box?.width).toBeLessThanOrEqual(301);
    const dims = await sidebar.evaluate((el) => {
      const body = el.querySelector("section")?.parentElement as HTMLElement;
      return { sw: body.scrollWidth, cw: body.clientWidth, asideSw: el.scrollWidth, asideCw: el.clientWidth };
    });
    expect(dims.sw).toBeLessThanOrEqual(dims.cw); // no horizontal scroll in the sidebar
    expect(dims.asideSw).toBeLessThanOrEqual(dims.asideCw);
    await expect(sidebar.getByRole("button", { name: "New project" })).toBeInViewport();
    const row = sidebar.getByRole("button", { name: `Open project ${LONG_NAME}` });
    const rowBox = await row.boundingBox();
    expect((rowBox?.x ?? 0) + (rowBox?.width ?? 0)).toBeLessThanOrEqual((box?.x ?? 0) + (box?.width ?? 0) + 1);
    expect(rowBox?.height).toBeLessThan(60);
    // The full name stays the accessible name and is shown in a tooltip on focus.
    await row.focus();
    await expect(page.getByRole("tooltip").filter({ hasText: LONG_NAME })).toHaveCount(1);

    // Main header, edit form and the page itself.
    const heading = page.getByRole("heading", { name: LONG_NAME });
    const hb = await heading.boundingBox();
    expect((hb?.x ?? 0) + (hb?.width ?? 0)).toBeLessThanOrEqual(size.width);
    await page.getByRole("button", { name: "Edit project details" }).click();
    const input = page.getByLabel("Name");
    await expect(input).toHaveValue(LONG_NAME);
    const ib = await input.boundingBox();
    expect((ib?.x ?? 0) + (ib?.width ?? 0)).toBeLessThanOrEqual(size.width);
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
    await noPageOverflow(page);
    await page.screenshot({ path: `${SHOTS}/long-name-${size.width}x${size.height}.png` });

    // Landing notice with the long name (missing project path uses an ID, so check home with the list).
    await page.getByRole("button", { name: "Back to all projects" }).click();
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await noPageOverflow(page);
  });
}

test("D2: a 240-character file name keeps the Files table, selection list and inspection panel bounded", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await blockExternal(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const id = await apiProject(page, unique("LongFile"), "long file name check");
  const longName = `${"f".repeat(236)}.csv`;
  expect(longName.length).toBe(240);
  await page.goto(`/#/projects/${id}/sources`);
  await expect(page.getByText(/no source files yet/i)).toBeVisible();

  await page.getByLabel("Choose files").setInputFiles([
    { name: longName, mimeType: "text/csv", buffer: Buffer.from("well_id,md_m,tvd_m\nA,0,0\n") },
    { name: "short.csv", mimeType: "text/csv", buffer: Buffer.from("well_id,md_m,tvd_m\nB,0,0\n") },
  ]);
  const selected = page.getByRole("list", { name: "Selected files" }).getByRole("listitem").first();
  expect((await selected.boundingBox())?.height).toBeLessThan(80);
  await noPageOverflow(page);
  await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
  await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });

  const table = page.getByRole("table", { name: "Files in this source revision" });
  const row = table.getByRole("row").filter({ has: page.getByRole("button", { name: `Edit labels for ${longName}` }) });
  await expect(row).toHaveCount(1);
  expect((await row.boundingBox())?.height).toBeLessThan(160); // bounded row height
  for (const name of [`Edit labels for ${longName}`, `Inspect extraction for ${longName}`]) {
    const target = page.getByRole("button", { name });
    await target.scrollIntoViewIfNeeded();
    const tb = await target.boundingBox();
    expect((tb?.x ?? 0) + (tb?.width ?? 0)).toBeLessThanOrEqual(1920); // other columns stay on screen
  }
  await noPageOverflow(page);

  // The full name is reachable from the keyboard: a button with the full value and a tooltip.
  const nameButton = row.getByRole("button", { name: `Copy file name: ${longName}` });
  // Even while the mouse rests on another truncated name, the focused button shows its own tooltip.
  await table.getByRole("button", { name: "Copy file name: short.csv" }).hover();
  await nameButton.focus();
  // The hovered tooltip fades out (it is briefly still in the DOM) while the focused one shows its value.
  await expect(page.getByRole("tooltip").filter({ hasText: longName })).toHaveCount(1);
  await expect(page.getByRole("tooltip").filter({ hasText: "short.csv" })).toHaveCount(0);
  await expect(page.getByRole("tooltip")).toHaveCount(1);
  await page.mouse.move(0, 0);

  // Inspection and editor panels stay inside the table width too.
  await page.getByRole("button", { name: `Inspect extraction for ${longName}` }).click();
  await page.getByRole("button", { name: `Edit labels for ${longName}` }).click();
  await expect(page.getByRole("form", { name: `Edit labels for ${longName}` })).toBeVisible();
  await noPageOverflow(page);
  await primaryControlsInside(page);
  await page.screenshot({ path: `${SHOTS}/long-filename-1920x1080.png` });
});

test("D6: the document outline has no skipped heading level on home and Sources", async ({ page }) => {
  await blockExternal(page);
  const id = await apiProject(page, unique("Outline"));
  for (const hash of ["/", `/projects/${id}/sources`]) {
    await page.goto(`/#${hash}`);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("heading").first()).toBeVisible();
    const result = await new AxeBuilder({ page }).withRules(["heading-order"]).analyze();
    expect(result.passes.length + result.incomplete.length).toBeGreaterThan(0);
    expect(result.violations.map((v) => v.id), `heading-order on ${hash}`).toEqual([]);
  }
});

test("D5: an unknown tab in the address is normalized to Sources", async ({ page }) => {
  await blockExternal(page);
  const id = await apiProject(page, unique("Bogus"));
  await page.goto(`/#/projects/${id}/bogus`);
  await expect(page.getByRole("navigation", { name: "Project sections" }).getByRole("button", { name: "Sources" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page).toHaveURL(new RegExp(`#/projects/${id}/sources$`));
});

for (const size of [
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
]) {
  test(`R1: revisions, files, job and inspection tables are not squeezed at ${size.width}x${size.height}`, async ({ page }) => {
    test.setTimeout(120_000);
    await blockExternal(page);
    await page.setViewportSize(size);
    const id = await apiProject(page, unique(`Squeeze ${size.width}`), "table geometry");
    await page.goto(`/#/projects/${id}/sources`);
    await page.getByLabel("Choose files").setInputFiles([
      { name: "synthetic.las", mimeType: "text/plain", buffer: Buffer.from(LAS) },
      { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("Field notes\nNothing structured.\n") },
    ]);
    await page.getByRole("button", { name: "Upload 2 file(s)" }).click();
    await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ }).click();
    await expect(page.getByText(/las_2_0 v/).first()).toBeVisible({ timeout: 60_000 });

    const revisions = page.getByRole("region", { name: "Source revisions table" }).locator("table");
    const metrics = await revisions.evaluate((table) => {
      const h = (el: Element) => Math.round(el.getBoundingClientRect().height);
      const w = (el: Element) => Math.round(el.getBoundingClientRect().width);
      const headers = [...table.querySelectorAll("thead th")];
      const body = table.querySelector("tbody tr");
      const cells = body ? [...body.children] : [];
      return {
        headers: headers.map((el) => ({ text: el.textContent ?? "", h: h(el), w: w(el), sw: (el as HTMLElement).scrollWidth })),
        cells: cells.map((el) => ({ h: h(el), w: w(el) })),
        chips: [...table.querySelectorAll("[data-tone]")].map((el) => h(el)),
        rowH: body ? h(body) : 0,
        tableW: w(table),
      };
    });
    for (const header of metrics.headers) {
      expect(header.h, `header "${header.text}" is not broken mid-word`).toBeLessThanOrEqual(60);
      expect(header.sw, `header "${header.text}" fits its column`).toBeLessThanOrEqual(header.w + 1);
    }
    expect(metrics.headers.map((x) => x.text)).toContain("Quarantined");
    for (const chip of metrics.chips) expect(chip, "status chip height bounded").toBeLessThanOrEqual(64);
    expect(metrics.rowH, "revision row height (Created, status, parent cells) bounded").toBeLessThanOrEqual(96);
    const minimums = [["Files", 36], ["Stored", 36], ["Quarantined", 70], ["Status", 150], ["Created", 120]] as const;
    for (const [name, min] of minimums) {
      const header = metrics.headers.find((x) => x.text.startsWith(name));
      expect(header?.w, `${name} column width`).toBeGreaterThanOrEqual(min);
    }
    expect(metrics.tableW).toBeLessThanOrEqual(size.width);

    // Every other table, definition list and chip in Sources (files table, job panel, inspection).
    const others = await page.getByRole("main").evaluate((main) => {
      const h = (el: Element) => Math.round(el.getBoundingClientRect().height);
      return {
        dt: [...main.querySelectorAll("dt")].map((el) => ({ t: el.textContent ?? "", h: h(el) })),
        th: [...main.querySelectorAll("th")].map((el) => ({ t: el.textContent ?? "", h: h(el) })),
        chips: [...main.querySelectorAll("[data-tone]")].map((el) => ({ t: el.textContent ?? "", h: h(el) })),
        // the full-width expansion row (inspection/editor) is legitimately tall; data rows are not
        rows: [...main.querySelectorAll("tbody tr")].filter((el) => !el.querySelector("td[colspan]")).map((el) => h(el)),
      };
    });
    expect(others.dt.length).toBeGreaterThan(5);
    for (const d of others.dt) expect(d.h, `term "${d.t}"`).toBeLessThanOrEqual(40);
    for (const t of others.th) expect(t.h, `header/row header "${t.t.slice(0, 20)}"`).toBeLessThanOrEqual(90);
    for (const c of others.chips) expect(c.h, `chip "${c.t.slice(0, 25)}"`).toBeLessThanOrEqual(64);
    for (const r of others.rows) expect(r, "table data row height").toBeLessThanOrEqual(160);
    await noPageOverflow(page);
    await page.screenshot({ path: `${SHOTS}/revisions-table-${size.width}x${size.height}.png`, fullPage: true });
  });
}

test("TASK-036 integration: populated candidates in the inspection panel use the kit and pass axe", async ({ page }) => {
  test.setTimeout(120_000);
  await blockExternal(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const id = await apiProject(page, unique("Candidates"), "candidate styling check");
  await page.goto(`/#/projects/${id}/sources`);
  await page.getByLabel("Choose files").setInputFiles([
    { name: "synthetic.las", mimeType: "text/plain", buffer: Buffer.from(LAS) },
  ]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByText("Ready (files stored; not extracted)")).toBeVisible({ timeout: 30_000 });

  const loc = { kind: "text", document_id: "d", source_revision_id: "r", line_start: 2, line_end: 2 };
  const base = {
    project_id: id, unit_id: "u1", source_revision_id: "r", document_id: "d", wellbore_id: null, subject: {},
    method: "model_proposal", evidence_class: "model_proposal", validation_state: "valid", state: "accepted",
    label: "model-proposed, rule-validated", reason_codes: [], validator_results: [],
    attributes: { kind: "measurement", attribute_key: "perforation.top_md", value_text: "4160.00", unit_as_written: "m", unit_defaulted: false },
    quote: "4160.00", evidence: { document_id: "d", source_revision_id: "r", locator: loc },
  };
  const items = [
    { ...base, candidate_id: "c1" },
    { ...base, candidate_id: "c2", state: "flagged", validation_state: "conflicting", label: "model-proposed, not accepted", reason_codes: ["parsed_conflict"], validator_results: [{ validator: "parsed_conflict", outcome: "flagged", reason: "parsed_conflict" }] },
    { ...base, candidate_id: "c3", state: "rejected", validation_state: "invalid", reason_codes: ["quote_not_in_span"] },
    { ...base, candidate_id: "c4", state: "candidate", method: "model_read", validation_state: "unverified", label: "model-read, unverified", reason_codes: ["model_read_unverified"], quote: null, attributes: { kind: "page_read", item_type: "packer", name: "Production packer", depth_text: "3064 m", sizes_text: [] }, evidence: { document_id: "d", source_revision_id: "r", locator: { kind: "pdf", document_id: "d", source_revision_id: "r", page: 3 } } },
  ];
  await page.route(/\/extraction-candidates/, (route) =>
    route.fulfill({ json: { items, page: { limit: 25, next_cursor: "more" } } }),
  );
  await page.getByRole("button", { name: /Inspect extraction for synthetic\.las/ }).click();
  const list = page.getByRole("list", { name: /Model-proposed candidates for synthetic\.las/ });
  await expect(list).toBeVisible({ timeout: 60_000 });
  await expect(list.getByRole("listitem")).toHaveCount(4);
  const heading = page.getByRole("heading", { name: "Model-proposed candidates", level: 6 });
  const sizes = await page.evaluate(() => {
    const h = [...document.querySelectorAll("h6")];
    return h.map((el) => parseFloat(getComputedStyle(el).fontSize));
  });
  for (const size of sizes) expect(size, "h6 headings are readable (>= 13 px)").toBeGreaterThanOrEqual(13);
  await heading.scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Load more candidates" })).toBeVisible();
  await expectNoSeriousAxe(page, "inspection with populated candidates");
  await page.screenshot({ path: `${SHOTS}/candidates-1920x1080.png`, fullPage: true });
});
