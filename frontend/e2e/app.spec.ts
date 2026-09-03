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

// 노선번호가 길거나 한글 지명이 붙은 실제 사례(30-5하남, 9401-1)와 자리수가 많은
// 번호를 함께 담아, 좁은 칸에서 번호가 쪼개지지 않는지 확인합니다.
const longNumberArrivals = {
  ...arrivals,
  items: ["30-5하남", "9401-1", "3500", "8146", "M6405"].map((busNumber, index) => ({
    bus_number: busNumber,
    direction: "강남역 방향",
    first_arrival_min: 2 + index,
    message: `${busNumber}번 버스가 약 ${2 + index}분 후 도착합니다.`,
    raw_arrmsg1: `${2 + index}분후[${index + 2}번째 전]`,
    raw_congestion1: "3",
    raw_is_last1: index === 4 ? "1" : "0",
    raw_bus_type1: index % 2 === 0 ? "1" : "0",
    raw_is_full_flag1: "0",
    raw_station_nm1: `테스트정류장${index + 1}`,
    raw_veh_id1: `long-${index + 1}`,
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
        transferCount: 0,
        payment: 1500,
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

// 3분 이내 도착 차량이 있으면서 목록도 여러 행을 채우는 조합입니다. 요약 띠는
// 담을 내용이 있을 때만 나오므로, 높이에 따른 접힘 규칙을 확인하려면 둘 다 필요합니다.
const soonAndListArrivals = {
  ...fiveRowArrivals,
  items: fiveRowArrivals.items.map((item, index) =>
    index < 2
      ? {
          ...item,
          first_arrival_min: index + 1,
          raw_arrmsg1: `${index + 1}분 후 [${index + 1}번째 전]`,
        }
      : item,
  ),
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

async function expectNoPageVerticalOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    viewportHeight: window.innerHeight,
    pageHeight: document.documentElement.scrollHeight,
  }));
  expect(metrics.pageHeight).toBeLessThanOrEqual(metrics.viewportHeight + 1);
}

async function installFakeRecorder(
  page: Page,
  options: { quiet?: boolean; stopDelayMs?: number } = {},
) {
  await page.addInitScript((recorderOptions) => {
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

/**
 * 화면이 뜬 뒤에 음성 동의를 부여합니다.
 *
 * 공용 키오스크는 마운트 시점에 이전 이용자의 동의를 지우므로, `addInitScript` 로
 * 미리 심어 둔 값은 남지 않습니다. 이는 의도된 개인정보 보호 동작입니다.
 */
async function grantVoiceConsent(page: Page) {
  await page.evaluate(() => localStorage.setItem("bitbox.voiceConsent.v1", "accepted"));
}

test.beforeEach(async ({ page }) => {
  // 이 기본 회귀 묶음은 제공자 쿼터와 운영 데이터를 절대 사용하지 않습니다.
  // localhost 이외의 요청은 모두 끊고, 각 API는 아래 테스트별 mock으로만 응답합니다.
  await page.route("**/*", (route) => {
    const hostname = new URL(route.request().url()).hostname;
    if (hostname === "127.0.0.1" || hostname === "localhost") return route.fallback();
    return route.abort("blockedbyclient");
  });
  await page.route("**/api/places/suggest?**", (route) => route.fulfill({ json: { suggestions: [] } }));
  await page.addInitScript(() => {
    class FakeUtterance {
      text: string;
      lang = "";
      rate = 1;
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) { this.text = text; }
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance });
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        speaking: false,
        // 한국어 음성이 설치된 정상 기기를 재현합니다. 음성이 없는 기기(라즈베리파이 등)는
        // 별도 테스트에서 서버 음성 대체를 확인합니다.
        getVoices: () => [{ lang: "ko-KR", name: "Korean", default: true, localService: true, voiceURI: "ko" }],
        addEventListener() {},
        removeEventListener() {},
        cancel() {
          const trackedWindow = window as Window & { __speechCancelCalls?: number };
          trackedWindow.__speechCancelCalls = (trackedWindow.__speechCancelCalls || 0) + 1;
          this.speaking = false;
        },
        speak(utterance: FakeUtterance) {
          const trackedWindow = window as Window & { __spokenPrompts?: string[] };
          trackedWindow.__spokenPrompts = [...(trackedWindow.__spokenPrompts || []), utterance.text];
          this.speaking = true;
          utterance.onstart?.();
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
  await expect(page.getByTestId("main-bus-row").first().getByText("3412", { exact: true })).toBeVisible();
  await expect(page.getByText("저상버스", { exact: true })).toBeVisible();
  // "잠시 후 도착" 요약은 전광판이 넉넉할 때만 나옵니다. 좁은 화면에서 이 패널을
  // 우선하면 정작 도착 목록이 한두 줄로 줄어드는데, 여기 실린 차량은 아래 목록에도
  // 그대로 나오므로 중복 요약보다 목록을 살리는 쪽이 맞습니다.
  await expect(page.getByTestId("soon-arrivals-panel")).toBeHidden();
  await expectNoHorizontalOverflow(page);
  await expectNoPageVerticalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("home.png"), fullPage: true });
});

test("shows the soon-arrivals summary only when it does not starve the arrival list", async ({ page }) => {
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: soonAndListArrivals }));

  // 세로가 넉넉한 전광판: 요약과 목록이 함께 들어갑니다.
  await page.setViewportSize({ width: 1280, height: 1024 });
  await page.goto("/");
  await expect(page.getByTestId("main-bus-row").first()).toBeVisible();
  await expect(page.getByTestId("soon-arrivals-panel")).toBeVisible();
  await expect.poll(() => page.getByTestId("main-bus-row").count()).toBeGreaterThanOrEqual(3);

  // 세로가 짧아지면 요약을 접고 목록에 자리를 내줍니다.
  await page.setViewportSize({ width: 1280, height: 720 });
  await expect(page.getByTestId("soon-arrivals-panel")).toBeHidden();
  await expect.poll(() => page.getByTestId("main-bus-row").count()).toBeGreaterThanOrEqual(3);
});

test("hides the soon-arrivals summary when nothing is arriving soon", async ({ page }) => {
  // 3분 이내 도착 차량이 하나도 없는 시간대(심야 등)입니다. 예전에는 이때도 노란
  // 띠가 그려져 "없습니다" 한 줄에 119px 을 썼고, 화면 위쪽이 통째로 비어 보였습니다.
  // 같은 사실은 아래 목록이 이미 보여 주므로 알릴 것이 있을 때만 자리를 내줍니다.
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));

  await page.setViewportSize({ width: 1280, height: 1024 });
  await page.goto("/");
  await expect(page.getByTestId("main-bus-row").first()).toBeVisible();
  await expect(page.getByTestId("soon-arrivals-panel")).toHaveCount(0);
  await expect(page.getByText("3분 이내 도착 예정 버스가 없습니다")).toHaveCount(0);
});

test("never slices a bus row or splits a route number across lines", async ({ page }) => {
  // 회귀: `break-all` 이 "3500" 을 "350"/"0" 두 줄로 쪼갰고, 페이지당 5행 고정이라
  // 큰 글씨 모드에서 5행 중 4행이 최대 228px 가려졌습니다. 둘 다 노선을 잘못 읽게
  // 만드는 문제라, 화면 크기·글씨 배율을 바꿔 가며 고정합니다.
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: longNumberArrivals }));

  for (const [width, height] of [[1280, 800], [1280, 720], [390, 844]] as const) {
    await page.setViewportSize({ width, height });
    for (const large of [false, true]) {
      await page.goto("/");
      if (large) await page.getByTitle("큰 글씨·고대비 화면으로 전환").click();
      await expect(page.getByTestId("main-bus-row").first()).toBeVisible();

      const problems = await page.evaluate(() => {
        const split: string[] = [];
        const sliced: string[] = [];
        const list = document.querySelector("[data-testid=main-bus-scroll]")!;
        const listBox = list.getBoundingClientRect();
        document.querySelectorAll<HTMLElement>("[data-testid=main-bus-row]").forEach((row) => {
          const box = row.getBoundingClientRect();
          const hidden =
            Math.max(0, listBox.top - box.top) + Math.max(0, box.bottom - listBox.bottom);
          if (hidden > 4) sliced.push(`${(row.textContent || "").trim().slice(0, 10)} ${Math.round(hidden)}px`);
          const number = row.querySelector<HTMLElement>("span[title$='번 버스']");
          if (!number) return;
          const lineHeight = Number.parseFloat(getComputedStyle(number).lineHeight);
          if (number.getBoundingClientRect().height > lineHeight * 1.5) {
            split.push((number.textContent || "").trim());
          }
        });
        return { split, sliced };
      });

      expect(problems.split, `노선번호 줄바꿈 ${width}x${height} large=${large}`).toEqual([]);
      expect(problems.sliced, `행 잘림 ${width}x${height} large=${large}`).toEqual([]);
    }
  }
});

test("large-text mode remains usable without horizontal clipping", async ({ page }) => {
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const stationName = page.getByTestId("station-name");
  const regularFontSize = await stationName.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
  await page.getByTitle("큰 글씨·고대비 화면으로 전환").click();
  await expect(page.locator("html")).toHaveAttribute("data-a11y-large", "");
  const largeFontSize = await stationName.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
  expect(largeFontSize).toBeGreaterThanOrEqual(regularFontSize * 1.19);
  const stationLayout = await stationName.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(stationLayout.scrollWidth).toBeLessThanOrEqual(stationLayout.clientWidth + 1);
  await expect(page.getByRole("combobox", { name: "버스 목적지" })).toBeVisible();
  await expect(page.getByTestId("main-bus-row").first()).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.setViewportSize({ width: 1280, height: 720 });
  await expect(page.getByRole("combobox", { name: "버스 목적지" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("destination input is bounded to the backend place-query limit", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("combobox", { name: "버스 목적지" });
  await input.fill("가".repeat(101));
  await expect(input).toHaveValue("가".repeat(100));
});

test("keeps every rendered bus row fully readable across target viewports", async ({ page }, testInfo) => {
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
    // 페이지당 행 수는 화면에 실제로 들어가는 만큼입니다. 억지로 채우면 큰 글씨
    // 모드나 낮은 화면에서 행이 잘려 노선을 잘못 읽게 됩니다.
    await expect.poll(() => rows.count()).toBeGreaterThanOrEqual(1);
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

    // 보여 준 행은 전부 영역 안에 들어가야 합니다. 무인 키오스크에서는 아무도
    // 스크롤하지 않으므로, 넘친 행은 없는 것과 같습니다.
    expect(metrics.scrollHeight, `${viewport.name} 목록이 넘침`)
      .toBeLessThanOrEqual(metrics.clientHeight + 1);
    const totalRowHeight = boxes.reduce((sum, box) => sum + box.height, 0);
    expect(totalRowHeight).toBeLessThanOrEqual(metrics.clientHeight + 1);

    // 반대 방향도 지킵니다. 한 행이 더 들어갈 자리가 남았는데 비워 두면, 세로로 긴
    // 창에서 목록 아래가 통째로 빈 화면이 됩니다(1180x1414 에서 367px 이 남았습니다).
    // 보여 줄 차량이 모자라 남는 경우는 레이아웃 문제가 아니므로, 다음 페이지가
    // 있을 때만 따집니다.
    //
    // 남는 높이는 실제 행 높이의 합이 아니라 "가장 높은 행 x 행 수" 를 기준으로 잽니다.
    // useVisibleRowCount 가 가장 높은 행을 기준으로 몇 행이 들어가는지 계산하기
    // 때문입니다. 정류장 이름이 길어 한 행만 두 줄이 되면 실제 합계는 작아지는데,
    // 그 차이를 레이아웃 결함으로 잡으면 정상 동작을 실패로 만듭니다.
    const hasMorePages = await page.getByLabel("다음 버스 목록").isVisible().catch(() => false);
    if (hasMorePages) {
      const tallestRow = Math.max(...boxes.map((box) => box.height));
      const roomForAnotherRow = metrics.clientHeight - boxes.length * tallestRow;
      expect(
        roomForAnotherRow,
        `${viewport.name} 목록에 ${Math.round(roomForAnotherRow)}px 이 남아 한 행을 더 담을 수 있는데 비워 둠`,
      ).toBeLessThan(tallestRow);
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
  const mapSdkRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("kakao.com/v2/maps/sdk.js")) mapSdkRequests.push(request.url());
  });
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
  await expect(page.getByText("환승 없음", { exact: true })).toBeVisible();
  await expect(page.getByText("예상 1,500원", { exact: true })).toBeVisible();
  await expect(page.getByText("출발지 출발")).toBeVisible();
  await expect(page.getByText("올림픽공원역 정류장 도착")).toBeVisible();
  expect(mapSdkRequests).toEqual([]);
  expect(requestBody.destination_x).toBe(127.0276);
  expect(requestBody.destination_y).toBe(37.4979);
  const recent = await page.evaluate(() => JSON.parse(localStorage.getItem("bitbox.recentDestinations") || "[]"));
  expect(recent[0]).toMatchObject({ name: "강남역 2호선", x: 127.0276, y: 37.4979 });
  await expectNoHorizontalOverflow(page);
  await expectNoPageVerticalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("route.png"), fullPage: true });

  await page.getByTitle("지도").click();
  await expect.poll(() => mapSdkRequests.length).toBeGreaterThan(0);
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
  await expect(page.getByTestId("soon-arrivals-panel")).toHaveCount(0);
});

test("keeps safety and speech status outside the route content", async ({ page }) => {
  await page.clock.install();
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();

  const safety = page.getByTestId("route-safety-panel");
  const routeContent = page.getByRole("region", { name: "경로 상세 내용" });
  const playback = page.getByTestId("playback-panel");
  await expect(safety).toBeVisible();
  await expect(routeContent).toBeVisible();
  await expect(playback).toBeVisible();

  const [safetyBox, routeBox, playbackBox] = await Promise.all([
    safety.boundingBox(),
    routeContent.boundingBox(),
    playback.boundingBox(),
  ]);
  expect(safetyBox).not.toBeNull();
  expect(routeBox).not.toBeNull();
  expect(playbackBox).not.toBeNull();
  expect(safetyBox!.y + safetyBox!.height).toBeLessThanOrEqual(routeBox!.y + 1);
  expect(playbackBox!.y).toBeGreaterThanOrEqual(routeBox!.y + routeBox!.height - 1);
});

test("keeps the route steps visible on a short screen while the guidance plays", async ({ page }) => {
  // 위 테스트의 픽스처는 짧은 노선번호와 한 문장짜리 안내라 헤더도 재생 패널도
  // 작습니다. 실제 환승 안내는 여러 문장이고 노선번호도 길어서, 그 조합에서만
  // 헤더가 부모보다 커지고 경로 단계 목록이 잘린 영역 밖으로 밀려났습니다.
  const busNumber = "30-5하남";
  const longGuidance = [
    "올림픽공원역 정류장까지 3분 걸어간 뒤 30-5하남번 버스를 타세요.",
    "잠실역 정류장에서 내려 146번 버스로 갈아타세요.",
    "강남역 정류장에서 내려 3분 걸으면 목적지에 도착합니다.",
    "전체 예상 시간은 62분이고 예상 요금은 1,500원입니다.",
  ].join(" ");
  const detail = routeResult.buses[0].routeDetail;
  await page.route("**/api/route", (route) => route.fulfill({ json: {
    ...routeResult,
    message: longGuidance,
    buses: [{
      ...routeResult.buses[0],
      busNumber,
      routeDetail: { ...detail, busNumber, transferCount: 1, payment: 1500 },
    }],
  } }));

  // 요청받은 짧은 화면 범위(600~664px)의 양 끝을 모두 확인합니다. 600px 는
  // 세로 예산이 훨씬 빠듯해 확보 가능한 높이가 다르므로 기대치를 따로 둡니다.
  for (const { height, minVisible } of [
    { height: 664, minVisible: 56 },
    { height: 600, minVisible: 24 },
  ]) {
    await page.setViewportSize({ width: 390, height });
    await page.goto("/");
    await page.getByLabel("버스 목적지").fill("강남역");
    await page.getByRole("button", { name: "버스 경로 검색" }).click();

    const routeContent = page.getByRole("region", { name: "경로 상세 내용" });
    const playback = page.getByTestId("playback-panel");
    await expect(routeContent).toBeVisible();
    await expect(playback).toBeVisible();

    // 요약은 헤더에서 아래 막대로 내려왔더라도 화면에 남아 있어야 합니다.
    await expect(page.getByText("환승 1회", { exact: true })).toBeVisible();
    await expect(page.getByText("예상 1,500원", { exact: true })).toBeVisible();

    const layout = await routeContent.evaluate((region) => {
      // 스크롤 영역이 자기 부모(overflow:hidden)의 바닥 아래로 밀려나면 화면에서
      // 사라집니다. boundingBox 만 보면 이 상태를 잡아내지 못합니다.
      const clip = region.parentElement!.getBoundingClientRect();
      const box = region.getBoundingClientRect();
      const panel = document
        .querySelector("[data-testid=playback-panel]")!
        .getBoundingClientRect();
      return {
        visibleHeight: Math.round(
          Math.max(0, Math.min(box.bottom, clip.bottom) - Math.max(box.top, clip.top)),
        ),
        overlap: Math.round(
          Math.max(0, Math.min(box.bottom, panel.bottom) - Math.max(box.top, panel.top)),
        ),
      };
    });
    // 회귀 당시 값: 664px 에서 보이는 높이 0px, 재생 패널이 48px 를 덮었습니다.
    expect(layout, `viewport 390x${height}`).toMatchObject({ overlap: 0 });
    expect(layout.visibleHeight, `viewport 390x${height}`).toBeGreaterThanOrEqual(minVisible);

    await expectNoHorizontalOverflow(page);
    await expectNoPageVerticalOverflow(page);
  }
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

test("explains an empty place search instead of showing a blank panel", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("존재하지않는장소");
  await expect(page.getByRole("status")).toContainText("일치하는 장소가 없습니다.");
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

test("keeps each bus page visible for ten seconds before rotating", async ({ page }) => {
  await page.clock.install();
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));
  await page.goto("/");
  await expect(page.getByTestId("main-bus-row").first()).toBeVisible();
  // 페이지당 행 수는 화면 높이에 따라 달라집니다. 회전 "주기"만 고정합니다.
  const firstRow = () => page.getByTestId("main-bus-row").first().innerText();
  const before = await firstRow();

  await page.clock.fastForward(9_000);
  expect(await firstRow(), "9초에는 아직 넘어가면 안 됩니다").toBe(before);

  await page.clock.fastForward(1_100);
  await expect.poll(firstRow, { timeout: 5_000 }).not.toBe(before);
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

  // 결과 안내 낭독이 시작된 뒤 종료 활동까지 반영하고, 그 이후의 실제 비활동
  // 90초를 잽니다. 낭독 중 초기화하지 않는 계약과 개인정보 상한을 함께 검증합니다.
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __spokenPrompts?: string[] }
  ).__spokenPrompts?.length || 0)).toBeGreaterThanOrEqual(1);
  await page.clock.fastForward(1_100);
  await page.clock.fastForward(90_000);
  await expect(page.getByRole("heading", { name: "어디로 갈까요?" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.recentDestinations"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.voiceConsent.v1"))).toBeNull();
});

test("listening to the guidance counts as using the kiosk", async ({ page }) => {
  // 안내를 듣는 동안은 화면을 만지지 않는 것이 정상입니다. 그것을 유휴로 세면
  // 낭독 도중에 결과가 사라집니다. 초기화 시간 자체는 90초 그대로여야 합니다.
  await page.clock.install();
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();

  await page.clock.fastForward(80_000);
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();

  // 안내 음성이 재생되면 유휴 시간을 다시 셉니다.
  await page.evaluate(() => window.dispatchEvent(new Event("bitbox:speech-activity")));

  // 검색 시점 기준으로는 이미 140초가 지났지만, 재생 기준으로는 60초입니다.
  await page.clock.fastForward(60_000);
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();

  // 그래도 자리를 뜨면 지워집니다. 개인정보 보장은 그대로입니다.
  await page.clock.fastForward(40_000);
  await expect(page.getByRole("heading", { name: "어디로 갈까요?" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.recentDestinations"))).toBeNull();
});

test("tracked-bus background speech does not extend route privacy", async ({ page }) => {
  await page.clock.install();
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __spokenPrompts?: string[] }
  ).__spokenPrompts?.length || 0)).toBeGreaterThanOrEqual(1);
  await page.clock.fastForward(1_100);

  await page.clock.fastForward(80_000);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent(
    "bitbox:speech-activity",
    { detail: { source: "background" } },
  )));
  await page.clock.fastForward(10_100);

  await expect(page.getByRole("heading", { name: "어디로 갈까요?" })).toBeVisible();
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

  await page.setViewportSize({ width: 390, height: 680 });
  await page.goto("/");
  await page.getByTitle("큰 글씨·고대비 화면으로 전환").click();
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();

  const confirmation = page.getByRole("group", { name: "강남역 2호선이 맞나요?" });
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
  const retryButton = confirmation.getByRole("button", { name: "다시 말하기" });
  await retryButton.scrollIntoViewIfNeeded();
  await expect(retryButton).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoPageVerticalOverflow(page);
  await primaryCandidate.click();

  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  expect(requestBodies).toHaveLength(2);
  expect(requestBodies[1].destination_x).toBe(127.02800140627488);
  expect(requestBodies[1].destination_y).toBe(37.49808633653005);
});

test("keeps a live arrival whose current station name is temporarily blank", async ({ page }) => {
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: {
    success: true,
    station_name: "올림픽공원역",
    station_id: "24245",
    message: "정상",
    items: [{
      bus_number: "3412",
      direction: "강남역 방향",
      first_arrival_min: 4,
      message: "4분 후 도착",
      raw_arrmsg1: "4분후",
      raw_station_nm1: "",
      raw_veh_id1: "blank-station-1",
    }],
  } }));

  await page.goto("/");
  const row = page.getByTestId("main-bus-row").filter({ hasText: "3412" });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("위치 확인 중");
  await expect(row).toContainText("4");
});

test("never clips the place confirmation question on a kiosk screen", async ({ page }) => {
  // 장소 확인은 이 서비스의 안전 설계가 드러나는 화면입니다. 질문이 잘리면 이용자는
  // 무엇을 확인해 달라는 것인지 읽을 수 없습니다. 세로로 잘린 글자는 axe 검사에도,
  // 텍스트 존재 여부를 보는 단언에도 걸리지 않으므로 실제 좌표로 확인합니다.
  //
  // 음성 경로는 텍스트 검색보다 화면에 담을 내용이 많습니다. 인식된 발화 한 줄과
  // 운영 서버가 실제로 돌려주는 두 줄짜리 판단 근거가 더 붙습니다. 짧은 목 데이터로는
  // 이 결함이 재현되지 않으므로 실제 응답과 같은 분량을 씁니다.
  await installFakeRecorder(page);
  await page.route("**/api/upload", async (route) => {
    await route.fulfill({
      json: {
        ...placeConfirmationResult,
        text: "잠실역 가는 버스를 알려줘.",
        safety_decision: {
          ...placeConfirmationResult.safety_decision,
          reasons: [
            "이름과 카테고리가 가장 적합한 후보를 우선했습니다.",
            "후보가 여러 개이므로 좌표를 확정하기 전에 질문합니다.",
          ],
        },
      },
    });
  });

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await grantVoiceConsent(page);
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await page.getByRole("button", { name: "음성 입력 완료" }).click();

  await expect(page.getByRole("heading", { name: "강남역 2호선이 맞나요?" })).toBeVisible();

  const bounds = await page.evaluate(() => {
    const scroller = document.querySelector('[data-testid="voice-panel-scroll"]');
    const title = document.getElementById("place-confirmation-title");
    if (!(scroller instanceof HTMLElement) || !title) return null;
    const panel = scroller.getBoundingClientRect();
    const question = title.getBoundingClientRect();
    return {
      hiddenAbove: Math.round(panel.top - question.top),
      hiddenBelow: Math.round(question.bottom - panel.bottom),
    };
  });

  expect(bounds).not.toBeNull();
  // 가운데 정렬된 스크롤 컨테이너에서 내용이 넘치면 위쪽은 스크롤로도 되돌릴 수 없어
  // 영영 읽을 수 없는 영역이 됩니다. 위아래 어느 쪽으로도 잘리면 안 됩니다.
  expect(bounds!.hiddenAbove).toBeLessThanOrEqual(0);
  expect(bounds!.hiddenBelow).toBeLessThanOrEqual(0);
});


test("clears an unanswered place confirmation after inactivity", async ({ page }) => {
  await page.clock.install();
  await page.route("**/api/route", (route) => route.fulfill({ json: placeConfirmationResult }));

  await page.goto("/");
  await page.getByLabel("버스 목적지").fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByRole("group", { name: "강남역 2호선이 맞나요?" })).toBeVisible();

  // 낭독 비동기 작업이 실제로 시작된 다음 종료 시점까지 진행해야, 종료 활동으로
  // 다시 설정된 90초 타이머를 정확히 검증할 수 있습니다.
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __spokenPrompts?: string[] }
  ).__spokenPrompts?.length || 0)).toBeGreaterThanOrEqual(1);
  await page.clock.fastForward(1_100);
  await page.clock.fastForward(90_000);
  await expect(page.getByRole("heading", { name: "어디로 갈까요?" })).toBeVisible();
  await expect(page.getByRole("group", { name: "강남역 2호선이 맞나요?" })).toHaveCount(0);
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
  await grantVoiceConsent(page);
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await expect(page.getByRole("button", { name: "음성 입력 완료" })).toBeVisible();
  await page.getByRole("button", { name: "음성 입력 완료" }).click();

  await expect(page.getByRole("group", { name: "강남역 2호선이 맞나요?" })).toBeVisible();
  expect(uploadContentType).toContain("multipart/form-data");
});

test("starts only one recorder when the microphone button is activated twice quickly", async ({ page }) => {
  await installFakeRecorder(page);
  await page.route("**/api/upload", (route) => route.fulfill({ json: terminalArrivalResult }));

  await page.goto("/");
  await grantVoiceConsent(page);
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
  await grantVoiceConsent(page);
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
  await grantVoiceConsent(page);
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
  await grantVoiceConsent(page);
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

// ---------------------------------------------------------------------------
// 개인정보 modal 이 실제 모달로 동작하는지
//
// `aria-modal="true"` 만으로는 배경 버튼이 계속 클릭·포커스됩니다. 배경을 실제로
// 비활성화하지 않으면 키보드·스크린리더 이용자의 포커스가 dialog 밖으로 새어 나가고
// 돌아오지 못합니다.
// ---------------------------------------------------------------------------

test("keeps focus and pointer input inside the privacy dialog", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "개인정보 처리 안내" }).click();
  const dialog = page.getByRole("dialog", { name: "음성·위치정보 처리 안내" });
  await expect(dialog).toBeVisible();

  // 초기 포커스가 dialog 안에 있어야 합니다.
  expect(await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"))).toBe(true);

  // 배경(버스 전광판)이 비활성화되어 포커스를 가져갈 수 없어야 합니다.
  const escaped = await page.evaluate(() => {
    const row = document.querySelector("[data-testid=main-bus-row]") as HTMLElement | null;
    if (!row) return { hasRow: false, stoleFocus: false, hitTestable: false };
    row.focus();
    const rect = row.getBoundingClientRect();
    const topElement = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return {
      hasRow: true,
      stoleFocus: document.activeElement === row,
      hitTestable: row.contains(topElement as Node),
    };
  });
  expect(escaped.hasRow).toBe(true);
  expect(escaped.stoleFocus).toBe(false);
  expect(escaped.hitTestable).toBe(false);

  // 여러 번 Tab 해도 포커스가 dialog 안에 머물러야 합니다.
  for (let index = 0; index < 10; index += 1) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"))).toBe(true);
  }
});

test("clears voice consent when the kiosk screen restarts", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem("bitbox.voiceConsent.v1", "accepted");
    localStorage.setItem("bitbox.recentDestinations", JSON.stringify([{ name: "우리집앞" }]));
  });
  await page.reload();
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();

  // 다시 뜬 화면 앞의 이용자는 직전 이용자와 다른 사람일 수 있습니다.
  expect(await page.evaluate(() => localStorage.getItem("bitbox.voiceConsent.v1"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.recentDestinations"))).toBeNull();

  // 따라서 마이크를 누르면 동의 화면이 다시 떠야 합니다.
  await page.getByRole("button", { name: "음성 입력 시작" }).click();
  await expect(page.getByRole("dialog", { name: "음성·위치정보 처리 안내" })).toBeVisible();
});

test("shows why a route has no arrival time instead of hiding it", async ({ page }) => {
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({
    json: {
      success: true,
      station_name: "올림픽공원역",
      station_id: "24245",
      message: "정상",
      items: [
        { bus_number: "101", direction: "차고지", message: "x", raw_arrmsg1: "출발대기", raw_station_nm1: "차고지" },
        { bus_number: "102", direction: "차고지", message: "x", raw_arrmsg1: "운행종료", raw_station_nm1: "차고지" },
        {
          bus_number: "3412", direction: "강남역 방향", first_arrival_min: 4, message: "x",
          raw_arrmsg1: "4분후[2번째 전]", raw_congestion1: "3", raw_bus_type1: "1",
          raw_station_nm1: "몽촌토성역", raw_veh_id1: "veh-live",
        },
      ],
    },
  }));
  await page.goto("/");
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();

  const rows = page.getByTestId("main-bus-row");
  await expect(rows).toHaveCount(3);

  // 노선이 사라지지 않고 이유가 보여야 합니다.
  await expect(page.getByText("출발 대기 중", { exact: true })).toBeVisible();
  await expect(page.getByText("운행 종료", { exact: true })).toBeVisible();

  // 그리고 그 노선이 "곧 도착"으로 읽히면 안 됩니다.
  const standbyRow = rows.filter({ hasText: "101" });
  await expect(standbyRow).not.toContainText("곧");
  await expect(standbyRow).toHaveAttribute("aria-label", /101번 버스, 출발 대기 중/);
  await expect(standbyRow).toBeDisabled();
  const terminalRow = rows.filter({ hasText: "102" });
  await expect(terminalRow).toHaveAttribute("aria-label", /102번 버스, 운행 종료/);
  await expect(terminalRow).toBeDisabled();

  // 실시간 차량은 그대로 앞에 옵니다.
  await expect(rows.first()).toContainText("3412");
});

test("does not announce the spoken guidance twice to a screen reader", async ({ page }) => {
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();

  const announcement = await page.evaluate(() => {
    const spoken: string[] = (window as unknown as { __spokenPrompts?: string[] }).__spokenPrompts || [];
    // role="status" 와 role="alert" 는 암묵적 live region 입니다. [aria-live] 만
    // 찾으면 이 둘에 안내 문구가 들어가도 통과해 버립니다.
    const live = Array.from(
      document.querySelectorAll("[aria-live], [role=status], [role=alert]"),
    )
      .map((node) => (node.textContent || "").trim())
      .filter(Boolean);
    return { spoken, live };
  });
  // 음성으로 재생되는 문장이 aria-live 에도 들어 있으면 두 번 들립니다.
  for (const text of announcement.spoken) {
    expect(announcement.live).not.toContain(text);
  }
});

test("lets the listener change the guidance volume and keeps it", async ({ page }) => {
  // 무인정보단말기 접근성 기준은 이용자가 음량을 조절할 수 있어야 한다고 요구합니다.
  // 정류장은 조용할 때도 있고 차 소리에 묻힐 때도 있어 한 값으로 맞출 수 없습니다.
  await page.goto("/");
  const quieter = page.getByLabel("안내 소리 작게");
  const louder = page.getByLabel("안내 소리 크게");
  const level = page.getByText(/^소리 \d$/);

  await expect(level).toHaveText("소리 5");
  await expect(louder).toBeDisabled();

  await quieter.click();
  await quieter.click();
  await expect(level).toHaveText("소리 3");
  await expect(louder).toBeEnabled();
  expect(await page.evaluate(() => localStorage.getItem("bitbox.speechVolume"))).toBe("0.6");

  // 무음 단계는 두지 않습니다. 화면을 보기 어려운 이용자에게 소리가 유일한 통로인데,
  // 앞사람이 꺼 둔 채로 남으면 다음 사람이 아무 안내도 받지 못합니다.
  await quieter.click();
  await quieter.click();
  await expect(level).toHaveText("소리 1");
  await expect(quieter).toBeDisabled();
  expect(Number(await page.evaluate(() => localStorage.getItem("bitbox.speechVolume")))).toBeGreaterThan(0);

  // 음량은 기기 설정이라 화면을 다시 켜도 남아 있어야 합니다. 시끄러운 정류장에서
  // 한 번 키워 둔 소리가 다음 사람에게도 들려야 합니다.
  await page.reload();
  await expect(page.getByText(/^소리 \d$/)).toHaveText("소리 1");
});

test("gives every board control a usable touch target", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));

  // 최근 목적지 칩도 조작 요소입니다. 그런데 이 앱은 공용 키오스크라 시작할 때마다
  // 이전 이용자의 기록을 지우므로(main.tsx), 저장소에 값을 심어 두는 방식으로는
  // 칩을 띄울 수 없습니다. 실제로 검색을 두 번 해서 칩을 만든 뒤 측정합니다.
  // 이 과정을 빼면 아래 크기·간격 검사가 칩을 아예 보지 못한 채 통과하고,
  // 실제로 그 상태에서 칩 사이 간격이 기준에 못 미치고 있었습니다.
  // 경로 결과에 버스가 없으면 화면은 검색 화면에 머무르고, 그때 최근 목적지 칩이
  // 보입니다. 결과 화면으로 넘어간 뒤 "처음으로" 를 누르면 공용 키오스크 정책상
  // 최근 기록이 지워지므로(resetKioskSession) 그 경로로는 칩을 관찰할 수 없습니다.
  await page.unroute("**/api/route");
  await page.route("**/api/route", (route) => route.fulfill({
    json: {
      success: true, text: "", intent: "route", destination: "", destination_text: "",
      message: "경로를 찾지 못했습니다.", buses: [], audio_base64: null,
      needs_confirmation: false, confirmation: null, safety_decision: null,
    },
  }));
  await page.goto("/");

  for (const place of ["강남역", "서울역"]) {
    await page.getByLabel("버스 목적지").fill(place);
    await page.getByRole("button", { name: "버스 경로 검색" }).click();
    await expect(page.getByTitle(`${place} 다시 검색`)).toBeVisible();
  }
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();

  // WCAG 2.2 AA (2.5.8 Target Size Minimum) 은 24x24 CSS px 이상을 요구합니다.
  const tooSmall = await page.evaluate(() => {
    const offenders: string[] = [];
    document.querySelectorAll<HTMLElement>("button,[role=button],a[href]").forEach((element) => {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      if (rect.width < 24 || rect.height < 24) {
        const label = (element.getAttribute("aria-label") || element.textContent || "").trim();
        offenders.push(`${Math.round(rect.width)}x${Math.round(rect.height)} ${label.slice(0, 24)}`);
      }
    });
    return offenders;
  });
  expect(tooSmall).toEqual([]);

  // 크기만 크면 되는 것이 아니라, 이웃한 조작 요소끼리 떨어져 있어야 합니다.
  // 무인정보단말기 접근성 기준은 12mm 버튼에 2.5mm 간격을 요구합니다(비율 0.21).
  // mm 는 실제 표시 장치 크기에 달려 있으므로 여기서는 비율로 확인합니다. 손이
  // 떨리는 이용자는 좁은 간격에서 옆 버튼을 누릅니다. 예전 페이지 제어는 44px
  // 버튼 사이가 6px(0.14)이었습니다.
  const crowded = await page.evaluate(() => {
    const boxes: { label: string; rect: DOMRect }[] = [];
    document.querySelectorAll<HTMLElement>("button,[role=button],a[href]").forEach((element) => {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const label = (element.getAttribute("aria-label") || element.textContent || "").trim();
      boxes.push({ label: label.slice(0, 24), rect });
    });
    const offenders: string[] = [];
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i].rect;
        const b = boxes[j].rect;
        const dx = Math.max(0, Math.max(a.left - b.right, b.left - a.right));
        const dy = Math.max(0, Math.max(a.top - b.bottom, b.top - a.bottom));
        if (dx === 0 && dy === 0) continue; // 겹치거나 포함 관계
        const gap = dx > 0 && dy > 0 ? Math.hypot(dx, dy) : Math.max(dx, dy);
        const smallestSide = Math.min(a.width, a.height, b.width, b.height);
        if (gap / smallestSide < 0.2) {
          offenders.push(
            `${boxes[i].label} ↔ ${boxes[j].label} : ${gap.toFixed(1)}px / ${Math.round(smallestSide)}px`,
          );
        }
      }
    }
    return offenders;
  });
  expect(crowded).toEqual([]);

  await expectNoHorizontalOverflow(page);
});

test("never clips route text vertically inside truncated cells", async ({ page }) => {
  // `truncate` 는 overflow:hidden 을 함께 켭니다. 줄높이가 글꼴의 자연 라인박스보다
  // 작으면 한글의 아래쪽 획이 잘립니다. 키오스크는 설치된 글꼴이 무엇일지 확정할 수
  // 없으므로 여유를 두고, 그 여유가 사라지지 않도록 여기서 고정합니다.
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({
    json: {
      success: true, station_name: "올림픽공원역", station_id: "24245", message: "정상",
      items: [{
        bus_number: "30-5하남", direction: "강남역 방향", first_arrival_min: 4, message: "x",
        raw_arrmsg1: "4분후[2번째 전]", raw_congestion1: "3", raw_bus_type1: "1",
        raw_station_nm1: "몽촌토성역", raw_veh_id1: "clip-1",
      }],
    },
  }));
  await page.setViewportSize({ width: 390, height: 680 });
  await page.goto("/");
  await page.getByTitle("큰 글씨·고대비 화면으로 전환").click();
  await expect(page.getByTestId("main-bus-row")).toHaveCount(1);
  const longBusNumber = page.getByTestId("main-bus-row").getByText("30-5하남", { exact: true });
  await expect(longBusNumber).toBeVisible();
  const busNumberLayout = await longBusNumber.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    textOverflow: getComputedStyle(element).textOverflow,
  }));
  expect(busNumberLayout.scrollWidth).toBeLessThanOrEqual(busNumberLayout.clientWidth + 1);
  expect(busNumberLayout.textOverflow).not.toBe("ellipsis");

  const clipped = await page.evaluate(() => {
    const offenders: string[] = [];
    document.querySelectorAll<HTMLElement>("span,div,strong,p,h2").forEach((element) => {
      if (element.children.length > 0) return;
      const text = (element.textContent || "").trim();
      if (!text) return;
      const style = getComputedStyle(element);
      if (style.overflow !== "hidden") return;
      const boxHeight = element.getBoundingClientRect().height;
      const previous = element.style.lineHeight;
      element.style.lineHeight = "normal";
      const naturalHeight = element.getBoundingClientRect().height;
      element.style.lineHeight = previous;
      if (naturalHeight - boxHeight > 0.5) {
        offenders.push(`${text.slice(0, 16)} box=${boxHeight.toFixed(1)} natural=${naturalHeight.toFixed(1)}`);
      }
    });
    return offenders;
  });
  expect(clipped).toEqual([]);
});

test("renders Korean with the bundled font instead of relying on the device", async ({ page }) => {
  // 키오스크에 CJK 글꼴이 없으면 정류장 이름이 두부(□□□)로 보입니다. 글꼴을 앱과 함께
  // 배포하고 실제로 그 글꼴이 로드되는지 고정합니다. CSP 는 font-src 'self' 만 허용하므로
  // 이 파일들은 반드시 같은 오리진에서 와야 합니다.
  const fontRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(".woff2")) fontRequests.push(new URL(request.url()).pathname);
  });

  await page.goto("/");
  await expect(page.getByText("올림픽공원역", { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  const loaded = await page.evaluate(() => {
    const faces = Array.from(document.fonts as unknown as Set<FontFace>);
    return {
      family: faces.map((face) => `${face.family}:${face.weight}:${face.status}`),
      canRenderBlackKorean: document.fonts.check('900 32px "Noto Sans KR"'),
    };
  });

  expect(loaded.canRenderBlackKorean).toBe(true);
  expect(loaded.family.some((entry) => entry.startsWith("Noto Sans KR"))).toBe(true);
  // 같은 오리진에서만 받아왔는지 (외부 CDN 이면 CSP 에 막혀 두부가 됩니다)
  expect(fontRequests.length).toBeGreaterThan(0);
  for (const path of fontRequests) expect(path.startsWith("/")).toBe(true);

  // 실제로 그려진 글꼴이 대체 글꼴이 아니라 번들 글꼴이어야 합니다.
  const usedFamily = await page.evaluate(() => {
    const node = Array.from(document.querySelectorAll("span")).find(
      (element) => (element.textContent || "").trim() === "올림픽공원역",
    );
    return node ? getComputedStyle(node).fontFamily : "";
  });
  expect(usedFamily).toContain("Noto Sans KR");
});

// ---------------------------------------------------------------------------
// 기기에 한국어 음성이 없을 때 (라즈베리파이 등) 안내가 무음이 되지 않는지
//
// 최소 설치 리눅스의 Chromium 은 음성 엔진이 없으면 speechSynthesis.speak() 가
// 오류 없이 아무 소리도 내지 않습니다. 교통약자용 키오스크에서 도착 안내가
// 들리지 않으면 핵심 기능이 사라지므로 서버 음성으로 대체되어야 합니다.
// ---------------------------------------------------------------------------

/** 음성 엔진이 설치되지 않은 기기를 재현합니다. */
async function installDeviceWithoutKoreanVoice(page: Page) {
  await page.addInitScript(() => {
    class SilentUtterance {
      text: string; lang = ""; rate = 1; voice: unknown = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) { this.text = text; }
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: SilentUtterance });
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        speaking: false,
        // 음성 목록이 영영 비어 있고 voiceschanged 도 오지 않습니다.
        getVoices: () => [],
        addEventListener() {},
        removeEventListener() {},
        cancel() {},
        speak() {
          const tracked = window as Window & { __silentSpeakCalls?: number };
          tracked.__silentSpeakCalls = (tracked.__silentSpeakCalls || 0) + 1;
        },
      },
    });
    // 재생 자체는 헤드리스에서 막히므로 호출만 기록합니다.
    const played: string[] = [];
    const paused: string[] = [];
    (window as Window & { __playedAudio?: string[] }).__playedAudio = played;
    (window as Window & { __pausedAudio?: string[] }).__pausedAudio = paused;
    const originalPlay = HTMLAudioElement.prototype.play;
    const originalPause = HTMLAudioElement.prototype.pause;
    HTMLAudioElement.prototype.play = function play(this: HTMLAudioElement) {
      played.push(this.src);
      return Promise.resolve();
    };
    HTMLAudioElement.prototype.pause = function pause(this: HTMLAudioElement) {
      paused.push(this.src);
      originalPause.call(this);
    };
    void originalPlay;
  });
}

test("falls back to server speech when the device cannot speak Korean", async ({ page }) => {
  await installDeviceWithoutKoreanVoice(page);

  const spokenTexts: string[] = [];
  await page.route("**/api/speech", async (route) => {
    spokenTexts.push(JSON.parse(route.request().postData() || "{}").text);
    // 아주 짧은 무음 WAV
    await route.fulfill({ json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" } });
  });
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));

  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();

  // 서버 음성으로 대체되었는지
  await expect.poll(() => spokenTexts.length).toBeGreaterThanOrEqual(1);
  // 노선번호는 정류장 안내처럼 자릿수로 끊어 읽습니다. "삼천사백십이 번"으로 읽으면
  // 청력이 떨어진 이용자가 화면의 3412 와 연결하지 못합니다.
  expect(spokenTexts[0]).toContain("삼사일이 번 버스");
  expect(spokenTexts[0]).not.toContain("3412");

  // 실제로 오디오 재생까지 이어졌는지
  const played = await page.evaluate(() => (window as Window & { __playedAudio?: string[] }).__playedAudio || []);
  expect(played.some((src) => src.startsWith("data:audio/wav"))).toBe(true);

  // 안내가 무음으로 끝나지 않았으므로 "재생하세요" 배너가 뜨면 안 됩니다.
  await expect(page.getByText("음성 안내를 재생해 주세요.")).toBeHidden();
});

test("falls back to server speech for tracked-bus arrival announcements", async ({ page }) => {
  await installDeviceWithoutKoreanVoice(page);

  const spokenTexts: string[] = [];
  await page.route("**/api/speech", async (route) => {
    spokenTexts.push(JSON.parse(route.request().postData() || "{}").text);
    await route.fulfill({ json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" } });
  });

  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({
    json: {
      success: true, station_name: "올림픽공원역", station_id: "24245", message: "정상",
      items: [{
        bus_number: "3412", direction: "강남역 방향", first_arrival_min: 1, message: "x",
        raw_arrmsg1: "곧 도착", raw_congestion1: "3", raw_bus_type1: "1",
        raw_station_nm1: "몽촌토성역", raw_veh_id1: "approach-1",
      }],
    },
  }));

  await page.goto("/");
  await expect(page.getByTestId("main-bus-row")).toHaveCount(1);

  // 버스를 추적 대상으로 선택하면 접근 알림이 나가야 합니다.
  await page.getByTestId("main-bus-row").first().click();
  await expect.poll(() => spokenTexts.length, { timeout: 8_000 }).toBeGreaterThanOrEqual(1);
  expect(spokenTexts.join(" ")).toContain("삼사일이 번 버스가 곧 도착합니다");

  // 브라우저 음성으로는 시도조차 하지 않아야 합니다(무음이 되므로).
  const silentCalls = await page.evaluate(() => (window as Window & { __silentSpeakCalls?: number }).__silentSpeakCalls || 0);
  expect(silentCalls).toBe(0);
});

test("bus polling never cancels an in-flight tracked-bus announcement", async ({ page }) => {
  await page.clock.install();
  await installDeviceWithoutKoreanVoice(page);

  let busCalls = 0;
  let speechRequests = 0;
  let releaseSpeech: () => void = () => {};
  const speechGate = new Promise<void>((resolve) => { releaseSpeech = resolve; });

  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", async (route) => {
    busCalls += 1;
    const remainingStops = busCalls === 1 ? 4 : busCalls === 2 ? 2 : 1;
    if (busCalls >= 3) releaseSpeech();
    await route.fulfill({ json: {
      success: true, station_name: "올림픽공원역", station_id: "24245", message: "정상",
      items: [{
        bus_number: "3412", direction: "강남역 방향", first_arrival_min: 5, message: "x",
        raw_arrmsg1: `5분후[${remainingStops}번째 전]`, raw_congestion1: "3",
        raw_bus_type1: "1", raw_station_nm1: "몽촌토성역", raw_veh_id1: "poll-safe-1",
      }],
    } });
  });
  await page.route("**/api/speech", async (route) => {
    speechRequests += 1;
    await speechGate;
    await route.fulfill({
      json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" },
    }).catch(() => {});
  });

  await page.goto("/");
  await page.getByTestId("main-bus-row").first().click();
  await page.clock.fastForward(15_000);
  await expect.poll(() => speechRequests).toBe(1);

  // 다음 폴링이 새 buses 배열과 remainingStops를 넣어도 기존 요청은 살아 있어야 합니다.
  await page.clock.fastForward(15_000);
  await expect.poll(() => busCalls).toBeGreaterThanOrEqual(3);
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __playedAudio?: string[] }
  ).__playedAudio?.length || 0)).toBe(1);
  expect(speechRequests).toBe(1);
});

// 추적하던 차량은 반드시 도착해서 떠나고, 떠나면 도착정보에서 사라집니다.
// 그때 추적 상태가 남아 있으면 무인 키오스크의 자동 페이지 전환이 영구히 멈춰
// 뒤에 온 이용자는 2페이지의 노선을 영영 볼 수 없습니다.
test("clears a tracked bus that has left so the board keeps rotating", async ({ page }) => {
  await page.clock.install();
  let trackedVehiclePresent = true;
  const boardOf = (present: boolean) => ({
    success: true, station_name: "올림픽공원역", station_id: "24245", message: "정상",
    items: Array.from({ length: 7 }, (_, index) => ({
      bus_number: String(3600 + index),
      direction: "강남역 방향",
      first_arrival_min: 10 + index,
      message: "x",
      // 0번 노선의 차량만 교체됩니다. 화면에 보이는 글자는 그대로이고
      // 차량 번호(추적 대상)만 달라지는, 실제로 버스가 떠난 상황입니다.
      raw_veh_id1: index === 0 ? (present ? "leaving-1" : "replacement-1") : `stay-${index}`,
      raw_arrmsg1: `${10 + index}분후[${index + 2}번째 전]`,
      raw_congestion1: "3", raw_bus_type1: "0",
      raw_station_nm1: `테스트정류장${index + 1}`,
    })),
  });

  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) =>
    route.fulfill({ json: boardOf(trackedVehiclePresent) }));

  await page.goto("/");
  await expect(page.getByTestId("main-bus-row").first()).toBeVisible();
  const firstRow = () => page.getByTestId("main-bus-row").first().innerText();
  const trackedPage = await firstRow();

  // 추적을 시작하면 자동 페이지 전환이 멈춥니다(의도된 동작).
  await page.getByTestId("main-bus-row").first().click();
  await page.clock.fastForward(10_000);
  expect(await firstRow(), "추적 중에는 페이지가 넘어가면 안 됩니다").toBe(trackedPage);

  // 추적하던 차량이 떠납니다. 폴링 두 번이면 일시적 누락이 아님이 확정됩니다.
  trackedVehiclePresent = false;
  await page.clock.fastForward(15_000);
  await page.clock.fastForward(15_000);

  // 추적이 풀렸으므로 자동 페이지 전환이 재개돼 다음 페이지가 보여야 합니다.
  // 추적이 남아 있으면 아무리 시간을 흘려보내도 같은 페이지에 머뭅니다.
  await expect.poll(async () => {
    await page.clock.fastForward(10_000);
    return firstRow();
  }, { timeout: 15_000 }).not.toBe(trackedPage);
});

// 안내가 재생 중일 때 통과한 임계값을 그냥 버리면, 가장 중요한 "곧 도착"이
// 영영 발화되지 않을 수 있습니다. 0정거장은 진행 중 안내를 대체해야 합니다.
test("an imminent arrival replaces an announcement that is still playing", async ({ page }) => {
  await page.clock.install();
  await installDeviceWithoutKoreanVoice(page);

  const spokenTexts: string[] = [];
  let releaseSpeech: () => void = () => {};
  const speechGate = new Promise<void>((resolve) => { releaseSpeech = resolve; });
  await page.route("**/api/speech", async (route) => {
    const text = JSON.parse(route.request().postData() || "{}").text;
    spokenTexts.push(text);
    // 첫 안내(세 정거장)는 붙잡아 두어 "재생 중" 상태를 유지합니다.
    if (spokenTexts.length === 1) await speechGate;
    await route.fulfill({
      json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" },
    }).catch(() => {});
  });

  let remainingStops = 4;
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: {
    success: true, station_name: "올림픽공원역", station_id: "24245", message: "정상",
    items: [{
      bus_number: "3412", direction: "강남역 방향", first_arrival_min: 5, message: "x",
      raw_arrmsg1: `5분후[${remainingStops}번째 전]`, raw_congestion1: "3",
      raw_bus_type1: "1", raw_station_nm1: "몽촌토성역", raw_veh_id1: "urgent-1",
    }],
  } }));

  await page.goto("/");
  await page.getByTestId("main-bus-row").first().click();

  // 3정거장 안내가 시작되고, 응답이 붙잡혀 재생 중 상태가 유지됩니다.
  remainingStops = 3;
  await page.clock.fastForward(15_000);
  await expect.poll(() => spokenTexts.length).toBe(1);
  expect(spokenTexts[0]).toContain("세 정거장");

  // 재생이 끝나기 전에 곧 도착에 진입합니다.
  remainingStops = 0;
  await page.clock.fastForward(15_000);

  await expect
    .poll(() => spokenTexts.join(" "), { timeout: 10_000 })
    .toContain("곧 도착합니다");
  releaseSpeech();
});

// 긴급하지 않은 임계값도 버리지 않고, 재생이 끝난 뒤 다시 평가되어야 합니다.
test("a threshold crossed during playback is announced once playback ends", async ({ page }) => {
  await page.clock.install();
  await installDeviceWithoutKoreanVoice(page);

  const spokenTexts: string[] = [];
  let releaseSpeech: () => void = () => {};
  const speechGate = new Promise<void>((resolve) => { releaseSpeech = resolve; });
  await page.route("**/api/speech", async (route) => {
    spokenTexts.push(JSON.parse(route.request().postData() || "{}").text);
    if (spokenTexts.length === 1) await speechGate;
    await route.fulfill({
      json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" },
    }).catch(() => {});
  });

  let remainingStops = 4;
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: {
    success: true, station_name: "올림픽공원역", station_id: "24245", message: "정상",
    items: [{
      bus_number: "3412", direction: "강남역 방향", first_arrival_min: 5, message: "x",
      raw_arrmsg1: `5분후[${remainingStops}번째 전]`, raw_congestion1: "3",
      raw_bus_type1: "1", raw_station_nm1: "몽촌토성역", raw_veh_id1: "pending-1",
    }],
  } }));

  await page.goto("/");
  await page.getByTestId("main-bus-row").first().click();

  remainingStops = 3;
  await page.clock.fastForward(15_000);
  await expect.poll(() => spokenTexts.length).toBe(1);

  // 재생 중에 한 정거장 전을 통과합니다. 지금은 발화하지 않지만 버려서도 안 됩니다.
  remainingStops = 1;
  await page.clock.fastForward(15_000);
  expect(spokenTexts).toHaveLength(1);

  // 재생이 끝나면 보관해 둔 임계값이 다시 평가되어야 합니다. 헤드리스에서는
  // 오디오 ended 이벤트가 오지 않으므로 30초 안전 해제 타이머로 종료시킵니다.
  //
  // 시계를 한 번만 앞당기면 안 됩니다. 재생이 끝난 **뒤에** 새로 잡히는 타이머는
  // 가상 시간이 더 흐르지 않으면 영영 발화하지 않는데, 폴링은 실제 시간으로만
  // 기다리기 때문입니다. 느린 러너에서 이 순서가 어긋나 CI 만 빨간불이 났습니다.
  // 확인할 때마다 시계를 함께 앞당겨, 어느 타이머에 실려 오든 잡습니다.
  releaseSpeech();
  await expect
    .poll(async () => {
      await page.clock.fastForward(10_000);
      return spokenTexts.join(" ");
    }, { timeout: 20_000 })
    .toContain("한 정거장 전");
});

test("a cancelled server speech request can never play after a newer announcement", async ({ page }) => {
  await installDeviceWithoutKoreanVoice(page);
  const requests: string[] = [];
  let releaseOldResponse: () => void = () => {};
  const oldResponseGate = new Promise<void>((resolve) => { releaseOldResponse = resolve; });
  await page.route("**/api/speech", async (route) => {
    const text = JSON.parse(route.request().postData() || "{}").text as string;
    requests.push(text);
    if (text === "이전 안내") await oldResponseGate;
    await route.fulfill({ json: { audio_base64: text === "이전 안내" ? "T0xE" : "TkVX" } }).catch(() => {});
  });

  await page.goto("/");
  await page.evaluate(async () => {
    const speech = await import("/src/utils/speech.ts");
    void speech.speakKorean("이전 안내");
  });
  await expect.poll(() => requests.length, { timeout: 4_000 }).toBe(1);

  await page.evaluate(async () => {
    const speech = await import("/src/utils/speech.ts");
    void speech.speakKorean("새 안내");
  });
  await expect.poll(() => requests.length, { timeout: 4_000 }).toBe(2);
  releaseOldResponse();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __playedAudio?: string[] }
  ).__playedAudio || [])).toHaveLength(1);

  const played = await page.evaluate(() => (
    window as Window & { __playedAudio?: string[] }
  ).__playedAudio || []);
  expect(played[0]).toContain("TkVX");
  expect(played[0]).not.toContain("T0xE");
});

test("a new announcement also stops pre-generated route audio", async ({ page }) => {
  const routeAudio = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=";
  await installDeviceWithoutKoreanVoice(page);
  await page.route("**/api/route", (route) => route.fulfill({
    json: { ...routeResult, audio_base64: routeAudio },
  }));
  await page.route("**/api/speech", (route) => route.fulfill({
    json: { audio_base64: "TkVX" },
  }));

  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __playedAudio?: string[] }
  ).__playedAudio || [])).toContainEqual(expect.stringContaining(routeAudio));

  await page.evaluate(async () => {
    const speech = await import("/src/utils/speech.ts");
    void speech.speakKorean("새 안내");
  });
  await expect.poll(() => page.evaluate(() => (
    window as Window & { __pausedAudio?: string[] }
  ).__pausedAudio || [])).toContainEqual(expect.stringContaining(routeAudio));
});

test("uses the browser voice and never calls the paid endpoint when one exists", async ({ page }) => {
  // 한국어 음성이 있는 기기에서는 서버 음성 비용이 발생하면 안 됩니다.
  let speechCalls = 0;
  await page.route("**/api/speech", async (route) => { speechCalls += 1; await route.fulfill({ json: {} }); });
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));

  await page.addInitScript(() => {
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        speaking: false,
        getVoices: () => [{ lang: "ko-KR", name: "Korean" }],
        addEventListener() {}, removeEventListener() {}, cancel() {},
        speak(utterance: { text: string; onstart?: () => void; onend?: () => void }) {
          const tracked = window as Window & { __spokenPrompts?: string[] };
          tracked.__spokenPrompts = [...(tracked.__spokenPrompts || []), utterance.text];
          utterance.onstart?.();
          queueMicrotask(() => utterance.onend?.());
        },
      },
    });
  });

  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();

  await expect.poll(() => page.evaluate(() => (window as Window & { __spokenPrompts?: string[] }).__spokenPrompts?.length || 0))
    .toBeGreaterThanOrEqual(1);
  expect(speechCalls).toBe(0);
});

test("falls back when a listed browser voice never starts", async ({ page }) => {
  let speechCalls = 0;
  await page.route("**/api/speech", async (route) => {
    speechCalls += 1;
    await route.fulfill({ json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" } });
  });
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.addInitScript(() => {
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        speaking: false,
        getVoices: () => [{ lang: "ko-KR", name: "Silent Korean" }],
        addEventListener() {}, removeEventListener() {}, cancel() {},
        // 실제 무음 실패처럼 start/error/end 어느 이벤트도 보내지 않습니다.
        speak() {},
      },
    });
  });

  await page.goto("/");
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByText("강남역 2호선 방면")).toBeVisible();
  await expect.poll(() => speechCalls, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
});

test("does not finish the UI before silent browser speech falls back", async ({ page }) => {
  let speechCalls = 0;
  await page.route("**/api/speech", async (route) => {
    speechCalls += 1;
    await route.fulfill({ json: { audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" } });
  });
  await page.route("**/api/route", (route) => route.fulfill({ json: routeResult }));
  await page.addInitScript(() => {
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        speaking: false,
        getVoices: () => [{ lang: "ko-KR", name: "Ends Without Starting" }],
        addEventListener() {}, removeEventListener() {}, cancel() {},
        speak(utterance: { onend?: () => void }) {
          queueMicrotask(() => utterance.onend?.());
        },
      },
    });
  });

  await page.goto("/");
  await page.evaluate(() => {
    HTMLAudioElement.prototype.play = function play() {
      // 서버 fallback이 실제 종료 신호를 기다리는 상태를 유지합니다.
      return Promise.resolve();
    };
  });
  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect.poll(() => speechCalls, { timeout: 5_000 }).toBe(1);
  await expect(page.getByRole("button", { name: "음성 중지" })).toBeVisible();
  await page.getByRole("button", { name: "음성 중지" }).click();
});

test("uses raw audio duration instead of blocking valid playback at 30 seconds", async ({ page }) => {
  await page.clock.install();
  await page.route("**/api/route", (route) => route.fulfill({
    json: {
      ...routeResult,
      audio_base64: "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=",
    },
  }));
  await page.goto("/");
  await page.evaluate(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "duration", {
      configurable: true,
      get: () => 45,
    });
    HTMLAudioElement.prototype.play = function play() {
      return Promise.resolve();
    };
  });

  await page.getByRole("combobox", { name: "버스 목적지" }).fill("강남역");
  await page.getByRole("button", { name: "버스 경로 검색" }).click();
  await expect(page.getByRole("button", { name: "음성 중지" })).toBeVisible();

  await page.clock.fastForward(31_000);
  await expect(page.getByRole("button", { name: "음성 중지" })).toBeVisible();
  await expect(page.getByText("음성 안내를 재생해 주세요.")).toBeHidden();

  await page.clock.fastForward(19_100);
  await expect(page.getByText("음성 안내를 재생해 주세요.")).toBeVisible();
});

test("reports a later server-speech chunk failure as partial", async ({ page }) => {
  await installDeviceWithoutKoreanVoice(page);
  const requestedTexts: string[] = [];
  await page.route("**/api/speech", async (route) => {
    requestedTexts.push(JSON.parse(route.request().postData() || "{}").text);
    if (requestedTexts.length === 1) {
      await route.fulfill({ json: { audio_base64: "UklGRg==" } });
    } else {
      await route.fulfill({ status: 503, json: { detail: "두 번째 조각 실패" } });
    }
  });
  await page.goto("/");
  await page.evaluate(() => {
    HTMLAudioElement.prototype.play = function play(this: HTMLAudioElement) {
      queueMicrotask(() => this.onended?.(new Event("ended")));
      return Promise.resolve();
    };
  });

  const outcome = await page.evaluate(async () => {
    const speech = await import("/src/utils/speech.ts");
    const message = `${"첫 번째 안내입니다. ".repeat(12)}${"두 번째 안내입니다. ".repeat(12)}`;
    return speech.speakKorean(message);
  });

  expect(outcome).toBe("partial");
  expect(requestedTexts.length).toBe(2);
  expect(requestedTexts.every((text) => text.length <= 200)).toBe(true);
});

test("keeps the bus list usable on short screens", async ({ page }) => {
  // 보드 세로 배치에서 스크롤 영역만 늘어나는 요소라, 화면이 낮으면 부족분을 전부
  // 흡수해 0px 로 접혔습니다. 그러면 버스 행이 표 머리글·푸터에 가려 눌리지 않습니다.
  // 1280x720 처럼 흔한 화면에서 실제로 발생했으므로 여기서 고정합니다.
  await page.unroute("**/api/bus/default");
  await page.route("**/api/bus/default", (route) => route.fulfill({ json: fiveRowArrivals }));

  for (const viewport of [
    { width: 1024, height: 600 },
    { width: 1280, height: 720 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    const firstRow = page.getByTestId("main-bus-row").first();
    await expect(firstRow).toBeVisible();

    const label = `${viewport.width}x${viewport.height}`;
    const scrollHeight = await page.evaluate(() => {
      const scroll = document.querySelector("[data-testid=main-bus-scroll]") as HTMLElement | null;
      return scroll ? Math.round(scroll.getBoundingClientRect().height) : 0;
    });
    expect(scrollHeight, `${label}: 목록 영역이 접혔습니다`).toBeGreaterThanOrEqual(100);

    // 가려져 있으면 이 클릭이 타임아웃납니다.
    await firstRow.click({ timeout: 5_000 });
    await expect(firstRow).toHaveAttribute("aria-pressed", "true");
    await firstRow.click({ timeout: 5_000 });
    await expectNoHorizontalOverflow(page);
    await expectNoPageVerticalOverflow(page);
  }
});
