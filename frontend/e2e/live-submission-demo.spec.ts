import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

type Cue = { id: string; startMs: number; durationMs: number; text: string };

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(currentDir, "../..");
const artifactDir = path.join(root, "artifacts");

const scenarios = [
  { query: "강남역", option: "강남역 2호선", bus: "3412", searchCue: "gangnam_search", resultCue: "gangnam_result" },
  { query: "서울역", option: "서울역 GTX-A", bus: "3214", searchCue: "seoul_search", resultCue: "seoul_result" },
  { query: "잠실역", option: "잠실역 2호선", bus: "3323", searchCue: "jamsil_search", resultCue: "jamsil_result" },
] as const;

const captions: Record<string, string> = {
  intro: "BITBOX 실제 작동 시연 · 실시간 버스 정보와 음성 길찾기",
  live: "실운영 모드 · Kakao 장소 검색 · ODsay 버스 경로 · OpenAI 음성 처리",
  gangnam_search: "시나리오 1 · 강남역 2호선 자동완성 선택",
  gangnam_result: "실제 경로 결과 · 3412번 · 약 44분 · 도보/승차 구간 안내",
  seoul_search: "시나리오 2 · 서울역 GTX-A 자동완성 선택",
  seoul_result: "실제 경로 결과 · 3214번 · 약 69분 · 다중 이동 구간 안내",
  jamsil_search: "시나리오 3 · 잠실역 2호선 자동완성 선택",
  jamsil_result: "실제 경로 결과 · 3323번 · 약 17분 · 안전 검증 완료",
  voice: "실제 음성 시나리오 · 마이크 입력 → STT → 장소 확인",
  confirm: "안전 설계 · 비슷한 장소는 임의 안내하지 않고 후보 확인",
  finish: "후보 선택 → 실시간 ODsay 경로 재조회 · 전체 기능 정상",
};

async function showCue(page: Page, cues: Cue[], startedAt: number, id: string, durationMs: number) {
  const text = captions[id];
  cues.push({ id, startMs: Date.now() - startedAt, durationMs, text });
  await page.evaluate(({ cueText }) => {
    let overlay = document.getElementById("submission-caption");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "submission-caption";
      Object.assign(overlay.style, {
        position: "fixed",
        left: "50%",
        bottom: "20px",
        transform: "translateX(-50%)",
        zIndex: "2147483647",
        width: "min(1120px, calc(100% - 40px))",
        padding: "14px 22px",
        border: "1px solid rgba(255,255,255,.3)",
        borderRadius: "12px",
        background: "rgba(5,18,22,.90)",
        color: "white",
        fontFamily: "Arial, sans-serif",
        fontSize: "24px",
        fontWeight: "800",
        lineHeight: "1.35",
        textAlign: "center",
        boxShadow: "0 12px 35px rgba(0,0,0,.35)",
        pointerEvents: "none",
      });
      document.body.appendChild(overlay);
    }
    overlay.textContent = cueText;
  }, { cueText: text });
  await page.waitForTimeout(durationMs);
}

async function resetToSearch(page: Page) {
  await page.getByRole("button", { name: "처음으로", exact: true }).click();
  await expect(page.getByRole("combobox")).toBeVisible({ timeout: 10_000 });
}

test("record live Hanium submission demo", async ({ page }) => {
  const cues: Cue[] = [];
  const startedAt = Date.now();
  await page.goto("/");
  await expect(page.getByRole("combobox")).toBeVisible({ timeout: 15_000 });
  await showCue(page, cues, startedAt, "intro", 9_000);
  await showCue(page, cues, startedAt, "live", 12_000);

  for (let index = 0; index < scenarios.length; index += 1) {
    const scenario = scenarios[index];
    const input = page.getByRole("combobox");
    await input.fill(scenario.query);
    const option = page.getByRole("option").filter({ hasText: scenario.option }).first();
    await expect(option).toBeVisible({ timeout: 15_000 });
    await showCue(page, cues, startedAt, scenario.searchCue, 10_000);
    await option.click();
    await page.locator('form button[type="submit"]').click();
    await expect(page.getByText(new RegExp(`${scenario.bus}번`)).first()).toBeVisible({ timeout: 30_000 });
    await showCue(page, cues, startedAt, scenario.resultCue, 12_000);

    const mapTab = page.locator(".route-tab").last();
    if (await mapTab.isVisible()) {
      await mapTab.click();
      await page.waitForTimeout(4_000);
    }
    if (index < scenarios.length - 1) await resetToSearch(page);
  }

  await resetToSearch(page);
  await showCue(page, cues, startedAt, "voice", 10_000);
  await page.locator("button.rounded-full").click();
  const privacyDialog = page.getByRole("dialog");
  if (await privacyDialog.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await privacyDialog.locator("footer button").last().click();
  }
  await expect(page.locator("button.rounded-full")).toBeEnabled({ timeout: 10_000 });
  await page.waitForTimeout(5_000);
  await page.locator("button.rounded-full").click();
  await expect(page.locator('[aria-labelledby="place-confirmation-title"]')).toBeVisible({ timeout: 45_000 });
  await showCue(page, cues, startedAt, "confirm", 11_000);
  await page.locator('[aria-labelledby="place-confirmation-title"] button').first().click();
  await expect(page.locator(".route-tab").first()).toBeVisible({ timeout: 30_000 });
  await showCue(page, cues, startedAt, "finish", 14_000);

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(path.join(artifactDir, "submission-cues.json"), JSON.stringify(cues, null, 2), "utf8");
});
