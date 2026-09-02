import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

type Cue = { id: string; startMs: number; durationMs: number; text: string };

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(currentDir, "../..");
const artifactDir = path.join(root, "artifacts");

const scenarios = [
  { query: "강남역", option: "강남역 2호선", searchCue: "gangnam_search", resultCue: "gangnam_result", mapCue: "gangnam_map" },
  { query: "서울역", option: "서울역 GTX-A", searchCue: "seoul_search", resultCue: "seoul_result", mapCue: "seoul_map" },
  { query: "잠실역", option: "잠실역 2호선", searchCue: "jamsil_search", resultCue: "jamsil_result", mapCue: "jamsil_map" },
] as const;

const captions: Record<string, string> = {
  intro: "BITBOX 실제 작동 시연 · 실시간 버스 정보와 음성 길찾기",
  live: "실데이터 연동 · Kakao 장소 검색 · ODsay 버스 경로 · OpenAI 음성 처리",
  gangnam_search: "시나리오 1 · 강남역 2호선 자동완성 선택",
  gangnam_result: "실시간 조회 결과 · 구간별 탑승·도보 안내와 검증 시각 확인",
  gangnam_map: "지도 보기 · 정류장 순서로 이은 예상 경로와 노선 번호",
  seoul_search: "시나리오 2 · 서울역 GTX-A 자동완성 선택",
  seoul_result: "실시간 조회 결과 · 환승 횟수·예상 요금·전체 이동시간 확인",
  seoul_map: "지도 보기 · 환승 구간을 색으로 구분해 표시",
  jamsil_search: "시나리오 3 · 잠실역 2호선 자동완성 선택",
  jamsil_result: "실시간 조회 결과 · 세 번째 목적지도 같은 절차로 독립 검증",
  jamsil_map: "지도 보기 · 출발·도착 표식과 전체 경로 자동 맞춤",
  voice: "음성 입력 시나리오 · 준비된 음성 샘플 → STT → 장소 확인",
  confirm: "안전 설계 · 비슷한 장소는 임의 안내하지 않고 후보 확인",
  finish: "후보 선택 → 실시간 경로 응답 화면 확인 · 시연 절차 완료",
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
        right: "20px",
        bottom: "20px",
        zIndex: "2147483647",
        width: "min(680px, calc(100% - 40px))",
        padding: "12px 16px",
        border: "1px solid rgba(255,255,255,.3)",
        borderRadius: "12px",
        background: "rgba(5,18,22,.90)",
        color: "white",
        fontFamily: "Arial, sans-serif",
        fontSize: "20px",
        fontWeight: "800",
        lineHeight: "1.35",
        textAlign: "left",
        // 기본 줄바꿈은 한국어를 어절 가운데서 끊어 "길찾/기" 처럼 갈라 놓습니다.
        wordBreak: "keep-all",
        boxShadow: "0 12px 35px rgba(0,0,0,.35)",
        pointerEvents: "none",
        transition: "opacity 180ms ease",
      });
      document.body.appendChild(overlay);
    }
    overlay.textContent = cueText;
    overlay.style.opacity = "1";
  }, { cueText: text });
  const visibleMs = Math.min(durationMs, 3_000);
  await page.waitForTimeout(visibleMs);
  await page.evaluate(() => {
    const overlay = document.getElementById("submission-caption");
    if (overlay) overlay.style.opacity = "0";
  });
  await page.waitForTimeout(Math.max(0, durationMs - visibleMs));
}

async function resetToSearch(page: Page) {
  await page.getByRole("button", { name: "처음으로", exact: true }).click();
  await expect(page.getByRole("combobox")).toBeVisible({ timeout: 10_000 });
}

test.skip(
  process.env.BITBOX_LIVE_DEMO_CONFIRM !== "4_LIVE_ROUTE_REQUESTS",
  "실경로 요청 4회를 승인하려면 BITBOX_LIVE_DEMO_CONFIRM=4_LIVE_ROUTE_REQUESTS를 명시하세요.",
);

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
    await expect(page.locator(".route-tab").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/번 탑승/).first()).toBeVisible({ timeout: 30_000 });
    await showCue(page, cues, startedAt, scenario.resultCue, 12_000);

    const mapTab = page.locator(".route-tab").last();
    if (await mapTab.isVisible()) {
      await mapTab.click();
      // 음성 재생 패널이 떠 있는 동안 720px 화면에서 지도에 남는 높이는 100px 남짓
      // 이라 경로선과 정류장 표식이 보이지 않습니다. 안내가 끝나기를 기다리면 긴
      // 경로에서 30초 넘게 멈춰 영상에 무음 구간이 생기므로, 화면에 이미 있는
      // "음성 중지" 조작을 그대로 눌러 패널을 내립니다. 시연 시간이 예측 가능해지고
      // 지도도 온전한 높이로 나옵니다.
      const stopSpeech = page.getByRole("button", { name: "음성 중지", exact: true });
      if (await stopSpeech.isVisible().catch(() => false)) await stopSpeech.click();
      await page
        .getByTestId("playback-panel")
        .waitFor({ state: "hidden", timeout: 15_000 })
        .catch(() => {});
      // 첫 지도는 SDK 를 받아 오느라 3~4초 뒤에야 타일이 그려집니다. 자막을 먼저
      // 띄우면 "예상 경로" 를 설명하는 동안 화면은 빈 흰 사각형입니다. 실제 타일이
      // 한 장이라도 붙은 뒤에 자막을 올립니다.
      await page
        .locator('img[src*="daumcdn.net"]')
        .first()
        .waitFor({ state: "visible", timeout: 20_000 })
        .catch(() => {});
      await showCue(page, cues, startedAt, scenario.mapCue, 9_000);
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
  // 정지 버튼을 누르지 않습니다. 이 앱은 발화가 끝나고 1.8초가 지나면 스스로 녹음을
  // 마칩니다(SILENCE_END_MS). 고령 이용자가 종료 조작을 하지 않아도 되게 만든 동작이므로
  // 시연에서도 그대로 보여 줍니다. 예전처럼 고정 시간 뒤에 버튼을 누르면, 이미 자동으로
  // 끝난 녹음에 대고 누르는 셈이라 오히려 새 녹음이 시작되고 확인 화면이 사라집니다.
  await expect(page.locator('[aria-labelledby="place-confirmation-title"]')).toBeVisible({ timeout: 60_000 });
  await showCue(page, cues, startedAt, "confirm", 11_000);
  await page.locator('[aria-labelledby="place-confirmation-title"] button').first().click();
  await expect(page.locator(".route-tab").first()).toBeVisible({ timeout: 30_000 });
  // 마지막 장면에서 안내 음성 패널이 떠 있으면 자막과 겹쳐 두 문장이 서로를 가립니다.
  // 지도 장면과 같은 "음성 중지" 조작으로 정리한 뒤 최종 화면을 담습니다.
  const stopFinalSpeech = page.getByRole("button", { name: "음성 중지", exact: true });
  if (await stopFinalSpeech.isVisible().catch(() => false)) await stopFinalSpeech.click();
  await page
    .getByTestId("playback-panel")
    .waitFor({ state: "hidden", timeout: 15_000 })
    .catch(() => {});
  await showCue(page, cues, startedAt, "finish", 14_000);

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(path.join(artifactDir, "submission-cues.json"), JSON.stringify(cues, null, 2), "utf8");
});
