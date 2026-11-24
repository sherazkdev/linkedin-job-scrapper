import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";
const stagingE2E = process.env.E2E_PILOT_READY === "1";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: stagingE2E ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/playwright-report.json" }]],
  use: {
    baseURL,
    trace: "on-first-retry",
    extraHTTPHeaders: stagingE2E
      ? { Origin: baseURL.replace(/\/$/, ""), "sec-fetch-site": "same-origin" }
      : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer:
    process.env.PLAYWRIGHT_NO_WEB_SERVER || stagingE2E
      ? undefined
      : {
          command: "npm run dev",
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            ...process.env,
            PILOT_API_BASE_URL: process.env.PILOT_API_BASE_URL ?? "http://127.0.0.1:18097",
            PUBLIC_JOBS_API_BASE_URL:
              process.env.PUBLIC_JOBS_API_BASE_URL ?? "http://127.0.0.1:18097",
            APP_URL: baseURL,
          },
        },
});