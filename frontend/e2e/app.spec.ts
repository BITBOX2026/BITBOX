import { expect, test, type Page } from "@playwright/test";

const arrivals = {
  success: true,
  station_name: "올림픽공원역",
  station_id: "24245",
  message: "정상",
  items: [
    {
      bus_number: "3412",
      direction: "강남역 방향",
      first_arrival_min: 2,
      second_arrival_min: 9,
      message: "3412번 버스가 약 2분 후 도착합니다.",
      raw_arrmsg1: "2분 후 [2번째 전]",
      raw_arrmsg2: "9분 후 [7번째 전]",
      raw_congestion1: "3",
      raw_congestion2: "4",
      raw_is_last1: "0",
      raw_is_last2: "0",
      raw_bus_type1: "1",
      raw_bus_type2: "0",
      raw_is_full_flag1: "0",
      raw_is_full_flag2: "0",
      raw_station_nm1: "몽촌토성역",
      raw_station_nm2: "잠실역",
      raw_veh_id1: "vehicle-3412-1",
      raw_veh_id2: "vehicle-3412-2",
    },
  ],
};

const routeResult = {
  success: true,
  destination: "강남역 2호선",
  destination_text: "강남역 2호선",
  message: "정류장까지 3분 걸어간 뒤 3412번 버스를 타세요.",
  audio_base64: null,
  buses: [
    {
      id: "route-3412-0",
      busNumber: "3412",
      arrivalMin: 2,
      traTimeSec: 120,
      arrivalMsg: "2분 후",
      currentStationName: "올림픽공원역 정류장",
      remainingStops: 2,
      busType: 0,
      congetion: 0,
      isFullFlag: false,
      isLastBus: false,
      plainNo: "",
      isSecond: false,
      routeDetail: {
        busNumber: "3412",
        totalMin: 30,
        origin: "올림픽공원역",
        origin_x: 127.121,
        origin_y: 37.516,
        destination_x: 127.0276,
        destination_y: 37.4979,
        steps: [
          { type: "walk", durationMin: 3, description: "도보 180m", fromStop: "출발지", toStop: "올림픽공원역 정류장" },
          { type: "bus", durationMin: 24, busNumber: "3412", fromStop: "올림픽공원역 정류장", toStop: "강남역 정류장" },
          { type: "walk", durationMin: 3, description: "도보 120m", fromStop: "강남역 정류장", toStop: "강남역" },
        ],
        route_segments: [
          {
            vehicle_type: "도보",
            line: "",
            start_name: "출발지",
            end_name: "올림픽공원역 정류장",
            time_min: 3,
            start_x: 127.121,
            start_y: 37.516,
            end_x: 127.119,
            end_y: 37.514,
            path_points: [
              { x: 127.121, y: 37.516 },
              { x: 127.119, y: 37.514 },
            ],
          },
          {
            vehicle_type: "버스",
            line: "3412",
            start_name: "올림픽공원역 정류장",
            end_name: "강남역 정류장",
            time_min: 24,
            start_x: 127.119,
            start_y: 37.514,
            end_x: 127.029,
            end_y: 37.499,
            path_points: [
              { x: 127.119, y: 37.514 },
              { x: 127.08, y: 37.51 },
              { x: 127.029, y: 37.499 },
            ],
          },
        ],
      },
    },
  ],
};

async function mockBoard(page: Page) {
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: arrivals }));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    class FakeUtterance {
      text: string;
      lang = "";
      rate = 1;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) { this.text = text; }
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance });
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        speaking: false,
        cancel() { this.speaking = false; },
        speak(utterance: FakeUtterance) {
          this.speaking = true;
          window.setTimeout(() => { this.speaking = false; utterance.onend?.(); }, 20);
        },
      },
    });
  });
  await mockBoard(page);
});

test("shows a stable live board on desktop and mobile", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();
  await expect(page.getByText("3412", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("저상버스", { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("home.png"), fullPage: true });
});

test("submits the exact autocomplete coordinates and renders walk steps", async ({ page }, testInfo) => {
  await page.route("**/api/places/suggest?**", (route) => route.fulfill({ json: {
    suggestions: [{ name: "강남역 2호선", address: "서울 강남구 강남대로 396", x: "127.0276", y: "37.4979" }],
  } }));
  let requestBody: Record<string, unknown> = {};
  await page.route("**/api/route", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ json: routeResult });
  });

  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남");
  await page.getByRole("option", { name: /강남역 2호선/ }).click();
  await page.getByRole("button", { name: "버스 경로 검색" }).click();

  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  await expect(page.getByText("도보 180m")).toBeVisible();
  await expect(page.getByText("3412번 탑승")).toBeVisible();
  await expect(page.getByText("출발지 출발")).toBeVisible();
  await expect(page.getByText("올림픽공원역 정류장 도착")).toBeVisible();
  expect(requestBody.destination_x).toBe(127.0276);
  expect(requestBody.destination_y).toBe(37.4979);
  const recent = await page.evaluate(() => JSON.parse(localStorage.getItem("bitbox.recentDestinations") || "[]"));
  expect(recent[0]).toMatchObject({ name: "강남역 2호선", x: 127.0276, y: 37.4979 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("route.png"), fullPage: true });

  await page.getByTitle("지도").click();
  await expect(page.getByText("정류장 기준 예상 경로")).toBeVisible();
  await expect(page.getByText("3412", { exact: true }).last()).toBeVisible();
  await expect(page.locator('img[src*="daumcdn.net"], img[src*="kakaocdn.net"]').first()).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: testInfo.outputPath("map.png"), fullPage: true });
});

test("supports keyboard autocomplete selection", async ({ page }) => {
  await page.route("**/api/places/suggest?**", (route) => route.fulfill({ json: {
    suggestions: [{ name: "강남역", address: "서울 강남구", x: "127.0276", y: "37.4979" }],
  } }));
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));

  await page.goto("/");
  const input = page.getByLabel("버스 목적지");
  await input.fill("강남");
  await expect(page.getByRole("option")).toBeVisible();
  await input.press("ArrowDown");
  await input.press("Enter");
  await input.press("Enter");
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
});

test("shows route server errors instead of an empty result", async ({ page }) => {
  await page.route("**/api/route", (route) => route.fulfill({ status: 503, json: { detail: "경로 서버를 사용할 수 없습니다." } }));
  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByRole("alert")).toContainText("경로 서버를 사용할 수 없습니다.");
});

test("handles denied microphone permission", async ({ page, context }) => {
  await context.clearPermissions();
  await page.goto("/");
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await expect(page.getByRole("dialog", { name: "음성·위치정보 처리 안내" })).toBeVisible();
  await page.getByRole("button", { name: "동의하고 마이크 사용" }).click();
  await expect(page.getByRole("alert")).toContainText("마이크를 사용할 수 없습니다");
});

test("requires voice consent and clears local recent destinations", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("bitbox.recentDestinations", JSON.stringify([{ name: "강남역" }])));
  await page.getByRole("button", { name: "음성 입력 시작" }).click();

  const dialog = page.getByRole("dialog", { name: "음성·위치정보 처리 안내" });
  await expect(dialog).toContainText("OpenAI로 전송");
  await dialog.getByRole("button", { name: "이 기기의 최근 목적지 삭제" }).click();
  await expect(dialog.getByText("최근 목적지를 삭제했습니다")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.recentDestinations"))).toBeNull();

  await dialog.getByRole("button", { name: "닫기", exact: true }).click();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.voiceConsent.v1"))).toBeNull();
});
