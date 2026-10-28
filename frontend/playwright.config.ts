import { defineConfig } from "@playwright/test";

// The npm script owns a fresh test database and API. Native or remote browsers use the same tests.
export default defineConfig({
  testDir: "./tests/e2e",
  workers: 1,
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:8101" },
  reporter: "list",
});
