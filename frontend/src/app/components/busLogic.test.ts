import { describe, expect, it } from "vitest";
import type { BusOption } from "../../types/bus";
import { accessibilityScore, describeBus, getApproachThreshold, toKoreanBoardError } from "./BusInfoList";
import { selectRecordingMimeType } from "../../hooks/useVoiceRecorder";

function bus(overrides: Partial<BusOption> = {}): BusOption {
  return {
    id: "vehicle-1",
    busNumber: "3214",
    status: "live",
    arrivalMin: 5,
    traTimeSec: 300,
    arrivalMsg: "5분 후",
    currentStationName: "몽촌토성역",
    remainingStops: 3,
    busType: 0,
    congestion: 3,
    isFullFlag: false,
    isLastBus: false,
    plainNo: "vehicle-1",
    isSecond: false,
    ...overrides,
  };
}

describe("accessibilityScore", () => {
  it("prefers a low-floor non-full vehicle", () => {
    expect(accessibilityScore(bus({ busType: 1 }))).toBeLessThan(
      accessibilityScore(bus({ isFullFlag: true })),
    );
  });

  it("does not rank unknown congestion as available seating", () => {
    expect(accessibilityScore(bus({ congestion: 0 }))).toBeGreaterThan(
      accessibilityScore(bus({ congestion: 3 })),
    );
  });
});

describe("selectRecordingMimeType", () => {
  it("uses mp4 when webm is unavailable", () => {
    expect(selectRecordingMimeType((type) => type === "audio/mp4")).toBe("audio/mp4");
  });

  it("allows the browser default when no candidate is supported", () => {
    expect(selectRecordingMimeType(() => false)).toBeUndefined();
  });
});

describe("describeBus", () => {
  it("summarizes an approaching bus as one screen-reader sentence", () => {
    const description = describeBus(bus({ traTimeSec: 30, congestion: 5, currentStationName: "잠실역" }));
    expect(description).toBe("3214번 버스, 곧 도착, 혼잡도 혼잡, 잠실역 통과");
  });

  it("includes low-floor, full, and last-bus flags when present", () => {
    const description = describeBus(bus({ busType: 1, isFullFlag: true, isLastBus: true }));
    expect(description).toContain("저상버스");
    expect(description).toContain("만차");
    expect(description).toContain("막차");
  });

  it("omits the location when currentStationName is missing", () => {
    const description = describeBus(bus({ currentStationName: "" }));
    expect(description).not.toContain("통과");
  });
});

describe("getApproachThreshold", () => {
  it("uses the most urgent crossed threshold when polling skips stops", () => {
    expect(getApproachThreshold(4, 0)).toBe(0);
    expect(getApproachThreshold(4, 2)).toBe(3);
    expect(getApproachThreshold(2, 1)).toBe(1);
  });

  it("does not repeat a threshold already announced", () => {
    expect(getApproachThreshold(2, 2)).toBeNull();
  });
});

describe("arrival status handling", () => {
  it("never reads a standby or terminal bus as arriving soon", () => {
    // traTimeSec = -1 을 시간 비교에 그대로 넣으면 "곧 도착"으로 잘못 읽힙니다.
    for (const status of ["standby", "terminal", "unknown"] as const) {
      const description = describeBus(bus({ status, arrivalMin: -1, traTimeSec: -1 }));
      expect(description).not.toContain("곧 도착");
      expect(description).not.toContain("분 후 도착");
    }
    expect(describeBus(bus({ status: "standby", arrivalMin: -1, traTimeSec: -1 })))
      .toBe("3214번 버스, 출발 대기 중");
    expect(describeBus(bus({ status: "terminal", arrivalMin: -1, traTimeSec: -1 })))
      .toBe("3214번 버스, 운행 종료");
  });

  it("sorts unavailable routes behind every boardable bus", () => {
    const boardable = accessibilityScore(bus({ isFullFlag: true, congestion: 5, arrivalMin: 29 }));
    const unavailable = accessibilityScore(bus({ status: "terminal", arrivalMin: -1, traTimeSec: -1 }));
    expect(unavailable).toBeGreaterThan(boardable);
  });
});

describe("toKoreanBoardError", () => {
  it("replaces the English abort reason with a Korean explanation", () => {
    const timeout = new DOMException("signal timed out", "TimeoutError");
    expect(toKoreanBoardError(timeout)).not.toContain("signal");
    expect(toKoreanBoardError(timeout)).toContain("시간이 오래 걸립니다");
  });

  it("keeps a Korean message that the server already produced", () => {
    expect(toKoreanBoardError(new Error("버스 도착정보 서비스를 사용할 수 없습니다.")))
      .toBe("버스 도착정보 서비스를 사용할 수 없습니다.");
  });

  it("falls back for any other technical failure", () => {
    expect(toKoreanBoardError(new Error("NetworkError when attempting to fetch")))
      .toBe("도착 정보를 불러오지 못했습니다.");
    expect(toKoreanBoardError("boom")).toBe("도착 정보를 불러오지 못했습니다.");
  });
});
