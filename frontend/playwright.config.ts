import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-results.json" }]],
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:3000", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { browserName: "chromium", launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {} } }],
});
