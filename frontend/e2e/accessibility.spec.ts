import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * 자동 접근성 규칙 검사 (axe-core).
 *
 * 이 제품의 이용자는 교통약자입니다. 접근성은 "의도"가 아니라 "검증"되어야 하므로,
 * 사람이 보지 않아도 깨지면 CI 가 막도록 주요 화면마다 WCAG 2.1 A/AA 규칙을 돌립니다.
 *
 * 한계: axe 는 기계가 판정할 수 있는 규칙만 봅니다. 실제 NVDA/VoiceOver/TalkBack 의
 * 낭독 순서·억양·중복 체감은 사람이 확인해야 하며 이 파일이 대신하지 못합니다.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const arrivals = {
  success: true,
  station_name: "올림픽공원역",
  station_id: "24245",
  message: "정상",
  items: [
    {
      bus_number: "3412", direction: "강남역 방향", first_arrival_min: 2, second_arrival_min: 9,
      message: "3412번 버스가 약 2분 후 도착합니다.",
      raw_arrmsg1: "2분 후 [2번째 전]", raw_arrmsg2: "9분 후 [7번째 전]",
      raw_congestion1: "3", raw_congestion2: "5", raw_is_last1: "0", raw_is_last2: "1",
      raw_bus_type1: "1", raw_bus_type2: "0", raw_is_full_flag1: "0", raw_is_full_flag2: "1",
      raw_station_nm1: "몽촌토성역", raw_station_nm2: "잠실역",
      raw_veh_id1: "a11y-1", raw_veh_id2: "a11y-2",
    },
    { bus_number: "101", direction: "차고지", message: "x", raw_arrmsg1: "출발대기", raw_station_nm1: "차고지" },
    { bus_number: "102", direction: "차고지", message: "x", raw_arrmsg1: "운행종료", raw_station_nm1: "차고지" },
  ],
};

const routeResult = {
  success: true, intent: "route", destination: "강남역 2호선", destination_text: "강남역 2호선",
  message: "올림픽공원역 정류장에서 3412번 버스를 타고 강남역 정류장에 내리세요. 약 30분 소요됩니다.",
  audio_base64: null, needs_confirmation: false, confirmation: null,
  safety_decision: {
    level: "verified", title: "검증 절차 완료",
    reasons: ["확정된 목적지 좌표를 기준으로 버스 경로를 조회했습니다."],
    auto_corrected: false, checked_at: "2026-08-26T02:00:00+09:00",
  },
  buses: [{
    id: "route-3412-0", busNumber: "3412", status: "live", arrivalMin: 2, traTimeSec: 120,
    arrivalMsg: "2분 후", currentStationName: "올림픽공원역 정류장", remainingStops: 2,
    busType: 0, congestion: 0, isFullFlag: false, isLastBus: false, plainNo: "", isSecond: false,
    routeDetail: {
      busNumber: "3412", totalMin: 30, origin: "올림픽공원역",
      steps: [
        { type: "walk", durationMin: 3, description: "도보 180m", fromStop: "출발지", toStop: "올림픽공원역 정류장" },
        { type: "bus", durationMin: 24, busNumber: "3412", fromStop: "올림픽공원역 정류장", toStop: "강남역 정류장" },
        { type: "walk", durationMin: 3, description: "도보 120m", fromStop: "강남역 정류장", toStop: "강남역" },
      ],
      route_segments: [],
    },
  }],
};

const placeConfirmation = {
  ...routeResult,
  message: "강남역 2호선이 맞나요?",
  needs_confirmation: true,
  buses: [],
  safety_decision: { level: "confirm", title: "장소 검증이 필요합니다", reasons: ["후보가 여러 개입니다."], auto_corrected: false },
  confirmation: {
    kind: "place", prompt: "강남역 2호선이 맞나요?",
    candidate: { name: "강남역 2호선", address: "서울 강남구 강남대로 396", category: "교통", category_code: "SW8", x: "127.0276", y: "37.4979" },
    alternatives: [{ name: "강남역 신분당선", address: "서울 강남구 강남대로 지하 396", category: "교통", category_code: "SW8", x: "127.0281", y: "37.4967" }],
  },
};

async function analyze(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
}

function summarize(violations: Awaited<ReturnType<typeof analyze>>["violations"]): string {
  return violations
    .map((violation) => `${violation.id} (${violation.impact}): ${violation.help}\n    ${violation.nodes.map((node) => node.target.join(" ")).slice(0, 4).join("\n    ")}`)
    .join("\n  ");
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: arrivals }));
  await page.route("**/api/places/suggest?**", (route) => route.fulfill({ json: { suggestions: [] } }));
  await page.addInitScript(() => {
    class FakeUtterance {
      text: string; lang = ""; rate = 1; onstart: (() => void) | null = null; onend: (() => void) | null = null; onerror: (() => void) | null = null;
      constructor(text: string) { this.text = text; }
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance });
    Object.defineProperty(window, "speechSynthesis", { value: {
      speaking: false,
      getVoices: () => [{ lang: "ko-KR", name: "Korean" }],
      addEventListener() {},
      removeEventListener() {},
      cancel() {},
      speak(utterance: { onstart?: (() => void) | null; onend?: (() => void) | null }) {
        utterance.onstart?.();
        queueMicrotask(() => utterance.onend?.());
      },
    } });
  });
});

test("home and live bus board have no automatic accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();
  const { violations } = await analyze(page);
  expect(summarize(violations)).toBe("");
});

test("route result screen has no automatic accessibility violations", async ({ page }) => {
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  const { violations } = await analyze(page);
  expect(summarize(violations)).toBe("");
});

test("place confirmation step has no automatic accessibility violations", async ({ page }) => {
  await page.route("**/api/route", (route) => route.fulfill({ json: placeConfirmation }));
  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선이 맞나요?")).toBeVisible();
  const { violations } = await analyze(page);
  expect(summarize(violations)).toBe("");
});

test("privacy dialog has no automatic accessibility violations", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "개인정보 처리 안내" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const { violations } = await analyze(page);
  expect(summarize(violations)).toBe("");
});

test("external failure state has no automatic accessibility violations", async ({ page }) => {
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({
    status: 502,
    json: { success: false, items: [], message: "버스 도착정보 서비스를 사용할 수 없습니다." },
  }));
  await page.goto("/");
  await expect(page.getByText("버스 도착정보 서비스를 사용할 수 없습니다.")).toBeVisible();
  const { violations } = await analyze(page);
  expect(summarize(violations)).toBe("");
});

test("screen reader tree exposes the board as named, operable controls", async ({ page }) => {
  // 스크린리더가 실제로 받아 가는 접근성 트리를 직접 확인합니다.
  await page.goto("/");
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();

  // 브라우저가 보조기술에 실제로 넘겨 주는 aria 트리를 그대로 받아 봅니다.
  const tree = await page.locator("body").ariaSnapshot();

  // 각 버스 행이 "번호 + 도착 + 혼잡도"를 한 문장으로 노출해야 합니다.
  expect(tree).toMatch(/button "3412번 버스, .*도착, 혼잡도/);
  // 도착정보가 없는 노선은 이유가 이름에 들어가야 합니다.
  expect(tree).toContain('101번 버스, 출발 대기 중');
  expect(tree).toContain('102번 버스, 운행 종료');
  // 스크롤 영역이 이름을 가진 채로 노출되어야 합니다.
  expect(tree).toContain('region "버스 도착 목록"');

  // 이름 없는 버튼이 하나도 없어야 합니다.
  const unnamedButtons = tree
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line === "- button" || line === "- button:");
  expect(unnamedButtons).toEqual([]);
});
