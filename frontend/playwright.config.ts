import { defineConfig, devices } from "@playwright/test";

const externalBaseUrl = process.env.PLAYWRIGHT_BASE_URL?.trim();

export default defineConfig({
  testDir: "./e2e",
  // 제출용 데모 녹화는 실제 백엔드·가짜 마이크·240초 타임아웃이 필요합니다.
  // playwright.submission.config.ts 로만 실행하고, 품질 게이트(npm run e2e)
  // 에서는 제외합니다. (제외하지 않으면 기본 30초 타임아웃에서 항상 실패합니다.)
  testIgnore: "live-submission-demo.spec.ts",
  // 키오스크는 Chromium 한 개로 동작합니다. 로컬·CI를 같은 단일 실행 조건으로
  // 고정해 머신 부하에 따른 음성/포털 타이밍 오탐을 없앱니다. 백엔드 동시성은
  // 별도 테스트가 담당합니다.
  fullyParallel: false,
  workers: 1,
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
