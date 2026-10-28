import { defineConfig } from "@playwright/test";

// E2E runs against the API serving the built SPA on 8101 (start it first; see docs).
export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: "http://127.0.0.1:8101" },
  reporter: "list",
});
