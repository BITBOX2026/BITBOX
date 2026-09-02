import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(currentDir, "..");
const fakeAudio = path.join(root, "artifacts", "submission-audio", "voice_input.wav");

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live-submission-demo.spec.ts",
  workers: 1,
  retries: 0,
  // 시나리오마다 안내 음성이 끝나기를 기다렸다가 지도를 담으므로 녹화가 길어집니다.
  timeout: 420_000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1280, height: 720 },
    video: { mode: "on", size: { width: 1280, height: 720 } },
    permissions: ["microphone"],
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        `--use-file-for-fake-audio-capture=${fakeAudio}`,
        "--autoplay-policy=no-user-gesture-required",
      ],
    },
  },
  outputDir: path.join(root, "artifacts", "submission-playwright"),
});
