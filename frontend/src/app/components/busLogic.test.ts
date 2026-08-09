import { describe, expect, it } from "vitest";
import type { BusOption } from "../../types/bus";
import { accessibilityScore, describeBus, getApproachThreshold } from "./BusInfoList";
import { selectRecordingMimeType } from "../../hooks/useVoiceRecorder";

function bus(overrides: Partial<BusOption> = {}): BusOption {
  return {
    id: "vehicle-1",
    busNumber: "3214",
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
