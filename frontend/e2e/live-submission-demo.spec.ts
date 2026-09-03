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

const configuredScenarioLimit = Number(process.env.BITBOX_DEMO_SCENARIO_LIMIT ?? scenarios.length);
const scenarioLimit = Number.isInteger(configuredScenarioLimit)
  ? Math.max(1, Math.min(scenarios.length, configuredScenarioLimit))
  : scenarios.length;
const activeScenarios = scenarios.slice(0, scenarioLimit);
const skipVoiceScenario = process.env.BITBOX_DEMO_SKIP_VOICE === "1";
const requiredLiveRouteRequests = scenarioLimit + (skipVoiceScenario ? 0 : 1);
const requiredConfirmation = `${requiredLiveRouteRequests}_LIVE_ROUTE_REQUESTS`;

// 자막에 줄바꿈을 넣을 때 이스케이프 대신 이 상수를 씁니다. 편집 도구를 거치며
// 역슬래시가 실제 줄바꿈으로 바뀌어 파일이 깨진 적이 있습니다.
const NL = String.fromCharCode(10);

const captions: Record<string, string> = {
  // 공모전 규정: 설명은 자막으로만 하고, 음성이 들어가면 시작에 고지해야 합니다.
  // 수치는 출처가 확인된 것만 씁니다. 20.3% 는 통계청 2025 고령자 통계,
  // 29.4% 는 NIA 2025 디지털정보격차 실태조사 84쪽 표 1(일반국민 대비 비율)입니다.
  intro: [
    "※ 본 영상에는 서비스의 음성 안내 기능 시연을 위한 음성이 포함되어 있습니다",
    "65세 이상이 인구의 20.3%",
    "70대 이상의 디지털 조작 역량은 일반국민 대비 29.4%",
  ].join(NL),
  live: [
    "정류장에서 큰 글씨와 음성만으로 버스를 찾는 안내 기기",
    "실시간 도착 정보를 큰 글씨로, 저상버스와 혼잡도를 함께 표시합니다",
  ].join(NL),
  gangnam_search: "타이핑 없이 목적지를 말하거나 골라서 찾습니다",
  gangnam_result: [
    "실제 대중교통 경로를 조회합니다",
    "환승 횟수와 예상 요금까지 한 화면에",
  ].join(NL),
  gangnam_map: "정류장 순서로 이은 경로를 지도로 확인합니다",
  voice: "음성 입력 시나리오 · 준비된 음성 샘플 → 인식 → 장소 확인",
  confirm: [
    "비슷한 지명은 임의로 안내하지 않고 되묻습니다",
    "잘못 안내하면 엉뚱한 곳에서 내리게 됩니다",
  ].join(NL),
  finish: [
    "글씨 크기와 안내 음량을 이용자가 직접 조절합니다",
    "공공 버스정보안내단말기의 표출 원칙을 따르고 오안내 방지 절차를 더했습니다",
  ].join(NL),
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
        transform: "translateX(-50%)",
        // 화면 아래에는 안내 음성이 재생될 때 노란 문구 막대가 뜹니다. 자막을 바닥에
        // 붙이면 그 문구를 덮어 두 글이 겹칩니다. 막대 높이만큼 띄웁니다.
        bottom: "104px",
        zIndex: "2147483647",
        width: "min(1120px, calc(100% - 48px))",
        padding: "14px 22px",
        borderRadius: "10px",
        background: "rgba(8,12,14,.86)",
        color: "white",
        fontFamily: "Arial, sans-serif",
        fontSize: "23px",
        fontWeight: "700",
        lineHeight: "1.45",
        textAlign: "center",
        // 자막 문구에 넣은 줄바꿈을 그대로 살립니다. 이걸 빼면 여러 줄이 한 줄로
        // 이어 붙어 화면 밖으로 밀립니다.
        whiteSpace: "pre-line",
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
  // 자막을 구간 내내 띄웁니다. 예전에는 3초 뒤 사라지게 해서, 완성본의 절반 이상이
  // 자막 없는 화면이었습니다. 공모전 규정은 설명을 자막으로 하라는 것이므로 화면에
  // 계속 남아 있어야 합니다.
  await page.waitForTimeout(durationMs);
}

async function resetToSearch(page: Page) {
  await page.getByRole("button", { name: "처음으로", exact: true }).click();
  await expect(page.getByRole("combobox")).toBeVisible({ timeout: 10_000 });
}

test.skip(
  process.env.BITBOX_LIVE_DEMO_CONFIRM !== requiredConfirmation,
  `실경로 요청 ${requiredLiveRouteRequests}회를 승인하려면 BITBOX_LIVE_DEMO_CONFIRM=${requiredConfirmation}를 명시하세요.`,
);

test("record live Hanium submission demo", async ({ page }) => {
  const cues: Cue[] = [];
  const startedAt = Date.now();
  await page.goto("/");
  await expect(page.getByRole("combobox")).toBeVisible({ timeout: 15_000 });
  await showCue(page, cues, startedAt, "intro", 9_000);
  await showCue(page, cues, startedAt, "live", 11_000);

  for (let index = 0; index < activeScenarios.length; index += 1) {
    const scenario = activeScenarios[index];
    const input = page.getByRole("combobox");
    await input.fill(scenario.query);
    const option = page.getByRole("option").filter({ hasText: scenario.option }).first();
    await expect(option).toBeVisible({ timeout: 15_000 });
    await showCue(page, cues, startedAt, scenario.searchCue, 8_000);
    await option.click();
    await page.locator('form button[type="submit"]').click();
    await expect(page.locator(".route-tab").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/번 탑승/).first()).toBeVisible({ timeout: 30_000 });
    await showCue(page, cues, startedAt, scenario.resultCue, 13_000);

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
      await showCue(page, cues, startedAt, scenario.mapCue, 11_000);
    }
    if (index < activeScenarios.length - 1) await resetToSearch(page);
  }

  if (!skipVoiceScenario) {
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
    await showCue(page, cues, startedAt, "finish", 13_000);
  } else {
    // 음성 시나리오를 건너뛰어도 마무리 자막은 남겨야 합니다. 이 자막이 차별점을
    // 말하는 유일한 구간이라, 빠지면 영상이 기능 나열로 끝납니다. 큰 글씨와 음량
    // 조절을 눌러 자막에서 말하는 내용을 화면으로도 보여 줍니다.
    await resetToSearch(page);
    await page.getByTitle("큰 글씨·고대비 화면으로 전환").click();
    await page.getByLabel("안내 소리 작게").click().catch(() => {});
    await page.getByLabel("안내 소리 크게").click().catch(() => {});
    await showCue(page, cues, startedAt, "finish", 13_000);
  }

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(path.join(artifactDir, "submission-cues.json"), JSON.stringify(cues, null, 2), "utf8");
});
