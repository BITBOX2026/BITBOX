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

const fiveRowArrivals = {
  ...arrivals,
  items: Array.from({ length: 7 }, (_, index) => ({
    bus_number: String(3500 + index),
    direction: "강남역 방향",
    first_arrival_min: 10 + index,
    message: `${3500 + index}번 버스가 약 ${10 + index}분 후 도착합니다.`,
    raw_arrmsg1: `${10 + index}분후[${index + 2}번째 전]`,
    raw_arrmsg2: "",
    raw_congestion1: "3",
    raw_congestion2: "0",
    raw_is_last1: "0",
    raw_is_last2: "0",
    raw_bus_type1: "0",
    raw_bus_type2: "0",
    raw_is_full_flag1: "0",
    raw_is_full_flag2: "0",
    raw_station_nm1: `테스트정류장${index + 1}`,
    raw_station_nm2: "",
    raw_veh_id1: `layout-vehicle-${index + 1}`,
    raw_veh_id2: "0",
  })),
};

const routeResult = {
  success: true,
  destination: "강남역 2호선",
  destination_text: "강남역 2호선",
  message: "정류장까지 3분 걸어간 뒤 3412번 버스를 타세요.",
  audio_base64: null,
  safety_decision: {
    level: "verified",
    title: "검증 절차 완료",
    reasons: ["확정된 목적지 좌표를 기준으로 버스 경로를 조회했습니다."],
    auto_corrected: false,
    checked_at: "2026-08-25T02:00:00+09:00",
  },
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
      congestion: 0,
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

const placeConfirmationResult = {
  success: true,
  destination: "강남역 2호선",
  destination_text: "강남역 2호선",
  message: "강남역 2호선이 맞나요?",
  buses: [],
  audio_base64: null,
  needs_confirmation: true,
  safety_decision: {
    level: "confirm",
    title: "장소 검증이 필요합니다",
    reasons: ["후보가 여러 개이므로 좌표를 확정하기 전에 질문합니다."],
    auto_corrected: false,
  },
  confirmation: {
    kind: "place",
    prompt: "강남역 2호선이 맞나요?",
    candidate: {
      name: "강남역 2호선",
      address: "서울 강남구 강남대로 지하 396",
      category: "교통,수송 > 지하철,전철 > 수도권2호선",
      category_code: "SW8",
      x: "127.02800140627488",
      y: "37.49808633653005",
    },
    alternatives: [
      {
        name: "강남역 신분당선",
        address: "서울 강남구 강남대로 지하 396",
        category: "교통,수송 > 지하철,전철 > 신분당선",
        category_code: "SW8",
        x: "127.028185245594",
        y: "37.4967771303817",
      },
    ],
  },
};

const terminalArrivalResult = {
  success: true,
  intent: "arrival",
  destination: "송파책박물관 정류장",
  destination_text: "송파책박물관 정류장",
  message: "3412번 버스는 운행이 종료되었습니다. 내일 첫차는 오전 5시 30분입니다.",
  buses: [],
  audio_base64: null,
  needs_confirmation: false,
  confirmation: null,
  safety_decision: {
    level: "verified",
    title: "검증 절차 완료",
    reasons: ["인식한 버스 번호를 운행 노선과 정확히 일치시켜 확인했습니다."],
    auto_corrected: false,
    checked_at: "2026-08-25T02:00:00+09:00",
  },
};

const unknownBusResult = {
  success: false,
  intent: "arrival",
  bus_number: "3423",
  destination: "올림픽공원역",
  message: "현재 정류장에서 3423번 노선을 확인하지 못했습니다. 버스 번호를 다시 말씀해 주세요.",
  buses: [],
  audio_base64: null,
  needs_confirmation: true,
  confirmation: null,
  safety_decision: {
    level: "retry",
    title: "다시 확인해 주세요",
    reasons: ["가장 가까운 번호로 자동 변경하지 않았습니다."],
    auto_corrected: false,
  },
};

async function mockBoard(page: Page) {
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: arrivals }));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
}

async function installFakeRecorder(
  page: Page,
  options: { quiet?: boolean; stopDelayMs?: number } = {},
) {
  await page.addInitScript((recorderOptions) => {
    localStorage.setItem("bitbox.voiceConsent.v1", "accepted");

    const trackedWindow = window as Window & {
      __getUserMediaCalls?: number;
      __stoppedAudioTracks?: number;
      __closedAudioContexts?: number;
    };
    trackedWindow.__getUserMediaCalls = 0;
    trackedWindow.__stoppedAudioTracks = 0;
    trackedWindow.__closedAudioContexts = 0;

    const stream = {
      getTracks: () => [{ stop() { trackedWindow.__stoppedAudioTracks = (trackedWindow.__stoppedAudioTracks || 0) + 1; } }],
    };

    class FakeAudioContext {
      state = "running";
      createAnalyser() {
        return {
          fftSize: 32,
          getByteFrequencyData(data: Uint8Array) { data.fill(recorderOptions.quiet ? 0 : 12); },
        };
      }
      createMediaStreamSource() { return { connect() {} }; }
      resume() { return Promise.resolve(); }
      close() {
        this.state = "closed";
        trackedWindow.__closedAudioContexts = (trackedWindow.__closedAudioContexts || 0) + 1;
        return Promise.resolve();
      }
    }

    class FakeMediaRecorder {
      static isTypeSupported() { return true; }
      state = "inactive";
      mimeType = "audio/webm";
      stream: typeof stream;
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      constructor(inputStream: typeof stream) { this.stream = inputStream; }
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        const finish = () => {
          this.ondataavailable?.({
            data: new Blob([new Uint8Array([0x1a, 0x45, 0xdf, 0xa3])], { type: "audio/webm" }),
          });
          this.onstop?.();
        };
        if (recorderOptions.stopDelayMs) window.setTimeout(finish, recorderOptions.stopDelayMs);
        else finish();
      }
    }

    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => {
          trackedWindow.__getUserMediaCalls = (trackedWindow.__getUserMediaCalls || 0) + 1;
          await new Promise((resolve) => window.setTimeout(resolve, 200));
          return stream;
        },
      },
    });
    Object.defineProperty(window, "AudioContext", { configurable: true, value: FakeAudioContext });
    Object.defineProperty(window, "webkitAudioContext", { configurable: true, value: FakeAudioContext });
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeMediaRecorder });
  }, options);
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/places/suggest?**", (route) => route.fulfill({ json: { suggestions: [] } }));
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
        cancel() {
          const trackedWindow = window as Window & { __speechCancelCalls?: number };
          trackedWindow.__speechCancelCalls = (trackedWindow.__speechCancelCalls || 0) + 1;
          this.speaking = false;
        },
        speak(utterance: FakeUtterance) {
          const trackedWindow = window as Window & { __spokenPrompts?: string[] };
          trackedWindow.__spokenPrompts = [...(trackedWindow.__spokenPrompts || []), utterance.text];
          this.speaking = true;
          window.setTimeout(() => { this.speaking = false; utterance.onend?.(); }, 1_000);
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

test("keeps five bus rows readable without overlap across target viewports", async ({ page }, testInfo) => {
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));

  const viewports = [
    { name: "mobile", width: 390, height: 844 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "desktop", width: 1280, height: 800 },
    { name: "kiosk", width: 1080, height: 1920 },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");

    const rows = page.getByTestId("main-bus-row");
    await expect(rows).toHaveCount(5);
    const metrics = await page.getByTestId("main-bus-scroll").evaluate((element) => ({
      clientHeight: element.clientHeight,
      clientWidth: element.clientWidth,
      scrollHeight: element.scrollHeight,
      scrollWidth: element.scrollWidth,
    }));
    const boxes = await rows.evaluateAll((elements) => elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        top: rect.top,
        bottom: rect.bottom,
        height: rect.height,
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
      };
    }));
    const expectedMinimumHeight = viewport.width >= 640 ? 68 : 56;

    for (const box of boxes) {
      expect(box.height).toBeGreaterThanOrEqual(expectedMinimumHeight);
      expect(box.scrollHeight).toBeLessThanOrEqual(box.clientHeight + 1);
    }
    for (let index = 1; index < boxes.length; index += 1) {
      expect(boxes[index].top).toBeGreaterThanOrEqual(boxes[index - 1].bottom - 0.5);
    }
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);

    const totalRowHeight = boxes.reduce((sum, box) => sum + box.height, 0);
    if (totalRowHeight <= metrics.clientHeight + 1) {
      expect(metrics.scrollHeight).toBeLessThanOrEqual(metrics.clientHeight + 1);
    } else {
      expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);
    }

    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`five-rows-${viewport.name}.png`), fullPage: true });
  }
});

test("cancels an active tracked-bus announcement when tracking is disabled", async ({ page }) => {
  await page.clock.install();
  await page.unroute("**/api/bus/default");
  let calls = 0;
  await page.route("**/api/bus/default", (route) => {
    calls += 1;
    const remainingStops = calls === 1 ? 4 : 2;
    return route.fulfill({ json: {
      ...fiveRowArrivals,
      items: fiveRowArrivals.items.map((item, index) => index === 0
        ? { ...item, raw_arrmsg1: `10분후[${remainingStops}번째 전]` }
        : item),
    } });
  });

  await page.goto("/");
  const trackedRow = page.getByTestId("main-bus-row").first();
  await trackedRow.click();
  await page.clock.fastForward(15_000);
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __spokenPrompts?: string[] }
  ).__spokenPrompts?.length || 0)).toBe(1);

  await trackedRow.click();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __speechCancelCalls?: number }
  ).__speechCancelCalls || 0)).toBeGreaterThanOrEqual(1);
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
  await expect(page.getByText("검증 절차 완료")).toBeVisible();
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
  await expect(
    page.locator('img[src*="daumcdn.net"], img[src*="kakaocdn.net"]').first()
      .or(page.getByText("지도 연결이 지연되어 정류장 순서로 표시합니다.")),
  ).toBeVisible({ timeout: 10_000 });
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

test("shows a place provider failure instead of an empty suggestion list", async ({ page }) => {
  await page.route("**/api/places/suggest?**", (route) => route.fulfill({
    status: 502,
    json: { detail: "장소 검색 서비스를 사용할 수 없습니다." },
  }));

  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await expect(page.getByRole("alert")).toContainText("장소 검색 서비스를 사용할 수 없습니다.");
});

test("coalesces two identical route submissions in the same interaction", async ({ page }) => {
  let routeCalls = 0;
  await page.route("**/api/route", async (route) => {
    routeCalls += 1;
    await new Promise((resolve) => setTimeout(resolve, 200));
    await route.fulfill({ json: routeResult });
  });

  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).evaluate((button) => {
    button.click();
    button.click();
  });
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  expect(routeCalls).toBe(1);
});

test("lets a user pause automatic bus page rotation", async ({ page }) => {
  await page.clock.install();
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));
  await page.goto("/");
  await expect(page.getByText("3500", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "자동 페이지 넘김 중지" }).click();
  await page.clock.fastForward(10_000);
  await expect(page.getByText("3500", { exact: true })).toBeVisible();
  await expect(page.getByText("3505", { exact: true })).toHaveCount(0);
});

test("clears a shared kiosk session after inactivity", async ({ page }) => {
  await page.clock.install();
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("bitbox.voiceConsent.v1", "accepted"));
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.recentDestinations"))).not.toBeNull();

  await page.clock.fastForward(90_000);
  await expect(page.getByRole("heading", { name: "어디로 갈까요?" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.recentDestinations"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.voiceConsent.v1"))).toBeNull();
});

test("clears voice consent after inactivity even when microphone permission fails", async ({ page, context }) => {
  await page.clock.install();
  await context.clearPermissions();
  await page.goto("/");
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await page.getByRole("button", { name: "동의하고 마이크 사용" }).click();
  await expect(page.getByRole("alert")).toContainText("마이크를 사용할 수 없습니다");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("bitbox.voiceConsent.v1"))).toBe("accepted");

  await page.clock.fastForward(90_000);

  await expect.poll(() => page.evaluate(() => localStorage.getItem("bitbox.voiceConsent.v1"))).toBeNull();
});

test("confirms an ambiguous station before requesting its route", async ({ page }) => {
  const requestBodies: Record<string, unknown>[] = [];
  await page.route("**/api/route", async (route) => {
    requestBodies.push(route.request().postDataJSON());
    await route.fulfill({ json: requestBodies.length === 1 ? placeConfirmationResult : routeResult });
  });

  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();

  const confirmation = page.getByRole("dialog", { name: "강남역 2호선이 맞나요?" });
  await expect(confirmation).toBeVisible();
  await expect(confirmation.getByRole("heading", { name: "강남역 2호선이 맞나요?" })).not.toHaveAttribute("aria-live");
  await expect(confirmation.getByText("강남역 신분당선")).toBeVisible();
  await expect(confirmation.getByText("장소 검증이 필요합니다")).toBeVisible();
  const primaryCandidate = confirmation.getByRole("button", { name: /강남역 2호선/ });
  await expect(primaryCandidate).toBeFocused();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __spokenPrompts?: string[] }
  ).__spokenPrompts?.length || 0)).toBeGreaterThanOrEqual(1);
  await confirmation.getByRole("button", { name: "질문 다시 듣기" }).click();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __spokenPrompts?: string[] }
  ).__spokenPrompts?.length || 0)).toBeGreaterThanOrEqual(2);
  await expectNoHorizontalOverflow(page);
  await primaryCandidate.click();

  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  expect(requestBodies).toHaveLength(2);
  expect(requestBodies[1].destination_x).toBe(127.02800140627488);
  expect(requestBodies[1].destination_y).toBe(37.49808633653005);
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

test("uploads a browser recording and opens place confirmation", async ({ page }) => {
  await installFakeRecorder(page);
  let uploadContentType = "";
  await page.route("**/api/upload", async (route) => {
    uploadContentType = route.request().headers()["content-type"] || "";
    await route.fulfill({ json: placeConfirmationResult });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await expect(page.getByRole("button", { name: "음성 입력 완료" })).toBeVisible();
  await page.getByRole("button", { name: "음성 입력 완료" }).click();

  await expect(page.getByRole("dialog", { name: "강남역 2호선이 맞나요?" })).toBeVisible();
  expect(uploadContentType).toContain("multipart/form-data");
});

test("starts only one recorder when the microphone button is activated twice quickly", async ({ page }) => {
  await installFakeRecorder(page);
  await page.route("**/api/upload", (route) => route.fulfill({ json: terminalArrivalResult }));

  await page.goto("/");
  const startButton = page.getByRole("button", { name: "음성 입력 시작" });
  await startButton.evaluate((button) => {
    button.click();
    button.click();
  });

  await expect(page.getByRole("button", { name: "마이크 준비 중" })).toBeDisabled();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __getUserMediaCalls?: number }
  ).__getUserMediaCalls || 0)).toBe(1);
  await page.getByRole("button", { name: "음성 입력 완료" }).click();
  await expect(page.getByText("운행이 종료되었습니다.").last()).toBeVisible();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __closedAudioContexts?: number }
  ).__closedAudioContexts || 0)).toBe(1);
});

test("does not upload a timed-out recording after a new recording starts", async ({ page }) => {
  await installFakeRecorder(page, { quiet: true, stopDelayMs: 500 });
  await page.clock.install();
  let uploadCalls = 0;
  await page.route("**/api/upload", (route) => {
    uploadCalls += 1;
    return route.fulfill({ json: terminalArrivalResult });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await page.clock.fastForward(200);
  await expect(page.getByRole("button", { name: "음성 입력 완료" })).toBeVisible();
  await page.clock.fastForward(8_000);
  await expect(page.getByRole("alert")).toContainText("음성이 감지되지 않았습니다");

  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await page.clock.fastForward(500);
  expect(uploadCalls).toBe(0);
});

test("renders terminal arrival as information instead of an error", async ({ page }) => {
  await installFakeRecorder(page);
  await page.route("**/api/upload", (route) => route.fulfill({ json: terminalArrivalResult }));

  await page.goto("/");
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await page.getByRole("button", { name: "음성 입력 완료" }).click();

  const informationCard = page.getByRole("heading", { name: "버스 운행 안내" }).locator("..");
  await expect(informationCard).toBeVisible();
  await expect(informationCard.getByText(/3412번 버스는 운행이 종료되었습니다/)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("explains that an unknown bus number was not automatically replaced", async ({ page }) => {
  await installFakeRecorder(page);
  await page.route("**/api/upload", (route) => route.fulfill({ json: unknownBusResult }));

  await page.goto("/");
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await page.getByRole("button", { name: "음성 입력 완료" }).click();

  const alert = page.getByRole("alert");
  await expect(alert).toContainText("3423번 노선을 확인하지 못했습니다");
  await expect(alert).toContainText("가장 가까운 번호로 자동 변경하지 않았습니다");
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
