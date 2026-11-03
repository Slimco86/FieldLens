// TASK-078 render smoke: the 3D canvas draws something for every asset-spec fixture and list
// selection updates the inspector. The asset-spec and exposure responses are mocked here (fixtures
// are only a test/e2e source); the project itself is real. Set FIELDLENS_SCENE_SHOTS=<dir> to also
// save screenshots and print the measured frame statistics.
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { blockExternal, createProject, projectId, unique } from "./project-support";

const FIXTURES = join(import.meta.dirname, "..", "fixtures", "asset-specs");
const CASES = ["f14-dimensioned", "f12-unlocated", "f5-generic"] as const;
interface Probe {
  nonBlank(): { total: number; different: number };
  measure(frames: number): unknown;
}
const SHOTS = process.env["FIELDLENS_SCENE_SHOTS"];

test.use({ launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] } });
test.setTimeout(90_000);
test.use({ viewport: { width: 1920, height: 1080 } });
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    (window as unknown as { __FIELDLENS_SCENE_PROBE__: boolean }).__FIELDLENS_SCENE_PROBE__ = true;
  });
  await blockExternal(page);
});

async function open(page: Page, file: string) {
  const spec = JSON.parse(readFileSync(join(FIXTURES, `${file}.json`), "utf8")) as Record<string, unknown>;
  const name = unique("Scene");
  await page.goto("/");
  await createProject(page, name, "3D smoke");
  const id = await projectId(page, name);
  const wellbore = String(spec["wellbore_id"]);
  await page.route(`**/api/v1/projects/${id}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const res = await route.fetch();
    const body = (await res.json()) as Record<string, unknown>;
    return route.fulfill({ response: res, json: { ...body, latest_source_revision_id: "00000000-0000-4000-8000-000000000001" } });
  });
  await page.route(`**/api/v1/projects/${id}/identity/exposure`, (route) =>
    route.fulfill({ json: { wells: [{ name: "Fixture well", wellbores: [{ wellbore_id: wellbore, wellbore_name: file }] }] } }),
  );
  await page.route(`**/api/v1/projects/${id}/wellbores/${wellbore}/asset-spec`, (route) =>
    route.fulfill({ json: { spec, status: "current", revision: 1 } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page.getByRole("navigation", { name: "Project sections" }).getByRole("button", { name: "Explore" }).click();
}

for (const file of CASES) {
  test(`scene renders non-blank: ${file}`, async ({ page }, info) => {
    await open(page, file);
    await expect(page.getByTestId("scene-canvas")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("illustrative-badge")).toBeVisible();
    await page.waitForFunction(() => (window as unknown as { __fieldlensSceneProbe?: unknown }).__fieldlensSceneProbe !== undefined, null, { timeout: 30_000 });
    await page.waitForTimeout(1500);
    const px = await page.evaluate(() => (window as unknown as { __fieldlensSceneProbe: Probe }).__fieldlensSceneProbe.nonBlank());
    expect(px.different).toBeGreaterThan(150);

    // Default view: wellhead + surface facilities + top of hole, with depth-scaled exaggeration.
    const stage = page.getByTestId("scene-stage");
    await expect(stage).toHaveAttribute("data-view", "wellhead");
    await expect(page.getByRole("toolbar", { name: "Scene controls" }).getByRole("button", { name: "Wellhead", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Fit whole well" })).toBeVisible();
    if (file === "f14-dimensioned") await expect(stage).toHaveAttribute("data-exaggeration", "5");
    await expect(page.getByTestId("scene-notes")).toContainText("exaggerated");
    if (SHOTS !== undefined) {
      mkdirSync(SHOTS, { recursive: true });
      await page.getByTestId("scene-canvas-wrap").scrollIntoViewIfNeeded();
      await page.waitForTimeout(1500);
      await page.getByTestId("scene-canvas-wrap").screenshot({ path: join(SHOTS, `default-${file}.png`) });
    }

    const first = page.locator("button[data-element-id]").first();
    await first.click();
    await expect(page.getByTestId("inspector-label")).toHaveText((await first.innerText()).split("\n")[0]!.trim());
    await expect(page.getByTestId("inspector-representation")).toBeVisible();

    if (SHOTS !== undefined) {
      mkdirSync(SHOTS, { recursive: true });
      await page.getByTestId("scene-label-layer").waitFor({ state: "attached" });
      await page.waitForTimeout(1500);
      await page.getByRole("button", { name: "Fit whole well" }).click();
      await page.getByTestId("scene-canvas-wrap").scrollIntoViewIfNeeded();
      await page.waitForTimeout(1500);
      await page.getByTestId("scene-canvas-wrap").screenshot({ path: join(SHOTS, `${file}.png`) });
      await page.getByRole("toolbar", { name: "Scene controls" }).getByRole("button", { name: "Wellhead", exact: true }).click();
      await page.waitForTimeout(1500);
      await page.getByTestId("scene-canvas-wrap").screenshot({ path: join(SHOTS, `${file}-surface.png`) });
      const un = page.getByRole("button", { name: "Unlocated", exact: true });
      if (await un.isEnabled()) {
        await un.click();
        await page.waitForTimeout(1500);
        await page.getByTestId("scene-canvas-wrap").screenshot({ path: join(SHOTS, `${file}-unlocated.png`) });
      }
      const stats = await page.evaluate(() => (window as unknown as { __fieldlensSceneProbe: Probe }).__fieldlensSceneProbe.measure(120));
      console.log(`SCENE_STATS ${file} ${JSON.stringify(stats)}`);
      info.annotations.push({ type: "stats", description: JSON.stringify(stats) });
    }
  });
}
