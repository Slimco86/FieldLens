// TASK-080 field view smoke (AG-8): all wellbores of a project in one scene, with the asset-spec
// and exposure responses mocked from the shared fixtures (the project itself is real). It checks
// the permanent badge and schematic-layout label, instancing, scene picking and list selection with
// fly-to, back-navigation from the wellbore view, and that GPU resources return to baseline after a
// rebuild and a tab switch. FIELDLENS_FIELD_WELLS (default 3) sets the number of wellbores with a
// spec; one more without a spec is always listed. FIELDLENS_SCENE_SHOTS=<dir> saves screenshots.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  blockExternal,
  createProject,
  projectId,
  unique,
} from "./project-support";

const FIXTURES = join(import.meta.dirname, "..", "fixtures", "asset-specs");
const FILES = ["f14-dimensioned", "f12-unlocated", "f5-generic"] as const;
const SPEC_WELLS = Math.max(
  3,
  Number(process.env["FIELDLENS_FIELD_WELLS"] ?? "3"),
);
const SHOTS = process.env["FIELDLENS_SCENE_SHOTS"];
const id = (n: number) =>
  `00000000-0000-4000-8000-0000000f${String(n).padStart(4, "0")}`;

interface Stats {
  frames: number;
  meanMs: number;
  p95Ms: number;
  maxMs: number;
  drawCalls: number;
  triangles: number;
  geometries: number;
  textures: number;
}
interface Probe {
  nonBlank(): { total: number; different: number };
  measure(frames: number): Stats;
}
interface FieldStats {
  wells: number;
  focusedId: string | null;
  glyphs: number;
  placeholders: number;
  markersShown: number;
  farDrawCalls: number;
}

test.use({
  launchOptions: {
    args: [
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  },
});
test.setTimeout(180_000);
test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ page }) => {
  // Deviated surveys for every other wellbore so the field has some shape (test-only source; no survey API exists yet).
  const trajectories: Record<string, unknown> = {};
  for (let i = 1; i < SPEC_WELLS; i += 2) {
    trajectories[id(i)] = {
      source: "fixture survey",
      stations: [
        { md_m: 0, tvd_m: 0 },
        { md_m: 600, tvd_m: 590 },
        { md_m: 1800, tvd_m: 1600, east_m: 220 * (1 + (i % 3)), north_m: 90 },
        {
          md_m: 4000,
          tvd_m: 3000,
          east_m: 650 * (1 + (i % 3)) * 0.8,
          north_m: 260,
        },
      ],
    };
  }
  await page.addInitScript((t) => {
    const w = window as unknown as Record<string, unknown>;
    w["__FIELDLENS_SCENE_PROBE__"] = true;
    w["__FIELDLENS_TEST_TRAJECTORY__"] = t;
    // Count WebGL contexts created and lost (the viewer must release its context when leaving Explore).
    const counters = { created: 0, lost: 0 } as {
      created: number;
      lost: number;
    };
    w["__glContexts"] = counters;
    const all: WebGL2RenderingContext[] = [];
    // "probe" = created on a canvas that was never attached to the document (capability probes);
    // "renderer" = a canvas in the document (R3F viewers).
    const tags: ("probe" | "renderer")[] = [];
    Object.defineProperty(counters, "probeLive", {
      get: () => all.filter((c, i) => tags[i] === "probe" && !c.isContextLost()).length,
      enumerable: true,
    });
    Object.defineProperty(counters, "probes", { get: () => tags.filter((t) => t === "probe").length, enumerable: true });
    Object.defineProperty(counters, "renderers", { get: () => tags.filter((t) => t === "renderer").length, enumerable: true });
    Object.defineProperty(counters, "lost", {
      get: () => all.filter((c) => c.isContextLost()).length,
      enumerable: true,
    });
    Object.defineProperty(counters, "live", {
      get: () =>
        all.filter(
          (c) =>
            !c.isContextLost() && (c.canvas as HTMLCanvasElement).isConnected,
        ).length,
      enumerable: true,
    });
    const orig = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      kind: string,
      ...rest: unknown[]
    ) {
      const ctx = (orig as (...a: unknown[]) => unknown).call(
        this,
        kind,
        ...rest,
      );
      if (
        ctx !== null &&
        kind === "webgl2" &&
        !(this as unknown as Record<string, unknown>)["__counted"]
      ) {
        (this as unknown as Record<string, unknown>)["__counted"] = true;
        counters.created += 1;
        all.push(ctx as WebGL2RenderingContext);
        tags.push(this.isConnected ? "renderer" : "probe");
      }
      return ctx;
    } as typeof orig;
  }, trajectories);
  await blockExternal(page);
});

async function openField(page: Page) {
  const name = unique("Field");
  await page.goto("/");
  await createProject(page, name, "Field view smoke");
  const pid = await projectId(page, name);
  const specIds = Array.from({ length: SPEC_WELLS }, (_, i) => id(i + 1));
  const missingId = id(900);
  const half = Math.ceil(specIds.length / 2);
  const exposure = {
    wells: [
      {
        name: "Alpha field",
        wellbores: specIds
          .slice(0, half)
          .map((w, i) => ({ wellbore_id: w, wellbore_name: `A-${i + 1}` })),
      },
      {
        name: "Beta field",
        wellbores: [
          ...specIds
            .slice(half)
            .map((w, i) => ({ wellbore_id: w, wellbore_name: `B-${i + 1}` })),
          { wellbore_id: missingId, wellbore_name: "B-new (no spec)" },
        ],
      },
    ],
  };
  await page.route(`**/api/v1/projects/${pid}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const res = await route.fetch();
    const body = (await res.json()) as Record<string, unknown>;
    return route.fulfill({
      response: res,
      json: {
        ...body,
        latest_source_revision_id: "00000000-0000-4000-8000-000000000001",
      },
    });
  });
  await page.route(`**/api/v1/projects/${pid}/identity/exposure`, (route) =>
    route.fulfill({ json: exposure }),
  );
  await page.route(
    `**/api/v1/projects/${pid}/wellbores/*/asset-spec`,
    (route) => {
      const wid = route.request().url().split("/wellbores/")[1]!.split("/")[0]!;
      const n = specIds.indexOf(wid);
      if (n < 0)
        return route.fulfill({
          status: 404,
          json: {
            error: { code: "not_found", message: "No spec", request_id: "r-1" },
          },
        });
      const spec = JSON.parse(
        readFileSync(join(FIXTURES, `${FILES[n % FILES.length]}.json`), "utf8"),
      ) as Record<string, unknown>;
      return route.fulfill({
        json: {
          spec: { ...spec, wellbore_id: wid },
          state: "current",
          revision: 1,
          spec_id: wid,
          created_at: "2026-11-02T20:00:00Z",
        },
      });
    },
  );
  await page.goto("/");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page
    .getByRole("navigation", { name: "Project sections" })
    .getByRole("button", { name: "Explore" })
    .click();
  return { specIds, missingId };
}

// Serious/critical axe violations (contrast of the illustrative badge, canvas wrapper role) must not regress.
async function expectNoSeriousAxe(page: Page, label: string) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const bad = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    bad.map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
    `axe serious/critical on ${label}`,
  ).toEqual([]);
}

const probe = (page: Page) =>
  page.evaluate(() =>
    (
      window as unknown as { __fieldlensSceneProbe: Probe }
    ).__fieldlensSceneProbe.measure(60),
  );
const fieldStats = (page: Page) =>
  page.evaluate(() =>
    (
      window as unknown as { __fieldlensFieldStats: () => FieldStats }
    ).__fieldlensFieldStats(),
  );
const waitProbe = (page: Page) =>
  page.waitForFunction(
    () =>
      (window as unknown as { __fieldlensFieldStats?: unknown })
        .__fieldlensFieldStats !== undefined,
    null,
    { timeout: 30_000 },
  );
const shot = async (page: Page, name: string) => {
  if (SHOTS === undefined) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.waitForTimeout(1500);
  await page
    .getByTestId("scene-canvas-wrap")
    .screenshot({ path: join(SHOTS, `${name}.png`) });
  await page.screenshot({ path: join(SHOTS, `${name}-page.png`) });
};

test(`field view: ${SPEC_WELLS} wellbores in one scene, selection, back-navigation, no leaks`, async ({
  page,
}) => {
  const { specIds, missingId } = await openField(page);
  await expect(page.getByTestId("scene-canvas")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("illustrative-badge")).toHaveText(
    "Illustrative visual — not an engineering model",
  );
  await expect(page.getByTestId("field-layout-label")).toContainText(
    "Schematic layout, not map positions",
  );
  await expect(page.getByTestId("field-summary")).toContainText(
    `${SPEC_WELLS + 1} wellbores: ${SPEC_WELLS} with asset spec, 1 without`,
  );
  await waitProbe(page);
  await page.waitForTimeout(1500);
  const px = await page.evaluate(() =>
    (
      window as unknown as { __fieldlensSceneProbe: Probe }
    ).__fieldlensSceneProbe.nonBlank(),
  );
  expect(px.different).toBeGreaterThan(300);

  // Every wellbore is listed, the one without a spec as a labelled entry; one instanced far set.
  const list = page.getByTestId("wellbore-list");
  await expect(list.locator("button[data-wellbore-id]")).toHaveCount(
    SPEC_WELLS + 1,
  );
  await expect(
    list.locator(`button[data-wellbore-id="${missingId}"]`),
  ).toContainText("No asset spec yet");
  const far = await fieldStats(page);
  expect(far).toMatchObject({
    wells: SPEC_WELLS + 1,
    glyphs: SPEC_WELLS,
    placeholders: 1,
  });
  expect(far.farDrawCalls).toBeLessThanOrEqual(5);
  await shot(page, `field-${SPEC_WELLS}-overview`);
  await expectNoSeriousAxe(page, "explore field view");

  const baseline = await probe(page);
  console.log(
    `FIELD_STATS wells=${SPEC_WELLS + 1} overview ${JSON.stringify(baseline)} far=${JSON.stringify(far)}`,
  );
  expect(baseline.drawCalls).toBeLessThanOrEqual(12);
  if (SHOTS !== undefined) {
    const longer = await page.evaluate(() =>
      (
        window as unknown as { __fieldlensSceneProbe: Probe }
      ).__fieldlensSceneProbe.measure(150),
    );
    console.log(
      `FIELD_STATS wells=${SPEC_WELLS + 1} overview150 ${JSON.stringify(longer)}`,
    );
  }

  // Scene picking: a click on a wellbore's pad selects it and flies there (instanced picking).
  const canvas = page.getByTestId("scene-canvas");
  const box = (await canvas.boundingBox())!;
  const at = await page.evaluate(
    (w) =>
      (
        window as unknown as {
          __fieldlensFieldScreen?: (
            id: string,
          ) => { x: number; y: number } | null;
        }
      ).__fieldlensFieldScreen?.(w) ?? null,
    specIds[0]!,
  );
  expect(at).not.toBeNull();
  await page.mouse.click(box.x + at!.x, box.y + at!.y);
  await expect(page.getByTestId("scene-stage")).toHaveAttribute(
    "data-selected",
    specIds[0]!,
  );

  // List selection (keyboard) selects another wellbore and flies; the inspector follows.
  const second = list.locator(`button[data-wellbore-id="${specIds[1]}"]`);
  await second.focus();
  await page.keyboard.press("Enter");
  await expect(second).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("field-inspector-name")).toContainText("A-2");
  await expect(page.getByTestId("scene-stage")).toHaveAttribute(
    "data-view",
    "focused",
  );
  const focused = await fieldStats(page);
  expect(focused.focusedId).toBe(specIds[1]);
  expect(focused.glyphs).toBe(SPEC_WELLS - 1);
  await shot(page, `field-${SPEC_WELLS}-focused`);

  // Leak check inside one renderer: rebuilding the far set and the focused wellbore returns to baseline counts.
  const before = await probe(page);
  await page.evaluate(() =>
    (
      window as unknown as { __fieldlensFieldRebuild: (n: number) => void }
    ).__fieldlensFieldRebuild(5),
  );
  await page.waitForTimeout(800);
  const after = await probe(page);
  console.log(
    `FIELD_LEAK rebuild geometries ${before.geometries}->${after.geometries} textures ${before.textures}->${after.textures}`,
  );
  expect(after.geometries).toBe(before.geometries);
  expect(after.textures).toBe(before.textures);

  // Selecting the selected wellbore opens the wellbore view; back-navigation returns to the field view with the selection kept.
  await second.click();
  await expect(page.getByTestId("back-to-field")).toBeVisible();
  await expect(
    page.getByRole("toolbar", { name: "Scene controls" }),
  ).toBeVisible();
  await expectNoSeriousAxe(page, "explore wellbore viewer");
  await page.getByTestId("back-to-field").click();
  await expect(page.getByTestId("field-summary")).toBeVisible();
  // Focus returns to the selected list item rather than falling to the page body.
  await expect(list.locator(`button[data-wellbore-id="${specIds[1]}"]`)).toBeFocused();
  await expect(
    list.locator(`button[data-wellbore-id="${specIds[1]}"]`),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("scene-canvas")).toBeVisible();

  // The wellbore without a spec is selectable and explained; Open leads to the empty state with its stub generator.
  await list.locator(`button[data-wellbore-id="${missingId}"]`).click();
  await expect(page.getByTestId("field-inspector")).toContainText(
    "placeholder ring",
  );
  await shot(page, `field-${SPEC_WELLS}-placeholder`);

  // Tab switch: leave Explore, come back; counts return to the fresh-renderer baseline and the context is released.
  const nav = page.getByRole("navigation", { name: "Project sections" });
  await nav.getByRole("button", { name: "Reconstruction" }).click();
  await expect(page.getByTestId("scene-canvas")).toHaveCount(0);
  await page.waitForTimeout(500);
  const ctx = await page.evaluate(() => {
    const c = (
      window as unknown as { __glContexts: { created: number; lost: number } }
    ).__glContexts;
    return {
      created: c.created,
      lost: c.lost,
      ...(c as unknown as { live: number; probeLive: number; probes: number; renderers: number }),
    };
  });
  expect(ctx.live).toBe(0);
  expect(ctx.probeLive).toBe(0);
  await nav.getByRole("button", { name: "Explore" }).click();
  await expect(page.getByTestId("scene-canvas")).toBeVisible({
    timeout: 30_000,
  });
  await waitProbe(page);
  await page.waitForTimeout(1500);
  const second2 = await probe(page);
  console.log(
    `FIELD_LEAK tab-switch geometries ${baseline.geometries}->${second2.geometries} textures ${baseline.textures}->${second2.textures} contexts ${JSON.stringify(ctx)}`,
  );
  expect(second2.geometries).toBe(baseline.geometries);
  expect(second2.textures).toBe(baseline.textures);
});
