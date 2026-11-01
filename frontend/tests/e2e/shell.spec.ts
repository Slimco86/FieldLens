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
  await expect(page.getByRole("button", { name: /remove|replace|delete|archive/i })).toHaveCount(0);

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
