import { defineConfig, devices } from "@playwright/test";

const externalBaseUrl = process.env.PLAYWRIGHT_BASE_URL?.trim();

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // Multi-context runs intermittently lost portal click feedback under runner
  // contention (1/20), while a single worker passed 50/50. A kiosk runs one
  // Chromium instance, so CI mirrors deployed browser concurrency; backend
  // concurrency remains tested separately.
  workers: process.env.CI ? 1 : undefined,
  forbidOnly: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: externalBaseUrl || "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"], browserName: "chromium" } },
  ],
  webServer: externalBaseUrl ? undefined : {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
