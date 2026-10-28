import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execute = promisify(execFile);

async function databaseState(state: "up" | "down") {
  await execute("uv", [
    "run", "--project", "..", "python", "../scripts/run_e2e.py", "--database-state", state,
  ]);
}

test.beforeEach(async ({ page }) => {
  await page.route("**/*", async (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host !== "127.0.0.1" && host !== "localhost") return route.abort("blockedbyclient");
    return route.continue();
  });
});

test("shell reports readiness and exposes no token in static output", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FieldLens" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Workspace" })).toBeVisible();
  const html = await page.content();
  expect(html).not.toMatch(/csrf_token|FIELDLENS_DB_PASSWORD/);
});

test("loading and network-error states are explicit, with keyboard retry recovery", async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const offline = async (route: import("@playwright/test").Route) => {
    await pending;
    await route.abort();
  };
  await page.route("**/ready", offline);
  try {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("status")).toHaveText("Checking local services…");
    release();
    await expect(page.getByRole("alert")).toContainText("The local API is unreachable.");
  } finally {
    release();
    await page.unroute("**/ready", offline);
  }
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Retry" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Local services ready.");
  await expect(page.getByRole("main")).toBeFocused();
});

test("real database failure stays unavailable on Retry and recovers without losing focus", async ({ page }) => {
  await databaseState("down");
  try {
    await page.goto("/");
    await expect(page.getByRole("alert")).toContainText("service is not ready");
    await expect(page.getByRole("heading", { name: "Workspace" })).toHaveCount(0);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Retry" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert")).toContainText("service is not ready");
    await expect(page.getByRole("main")).toBeFocused();
  } finally {
    await databaseState("up");
  }
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Retry" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Local services ready.");
  await expect(page.getByRole("main")).toBeFocused();
});
