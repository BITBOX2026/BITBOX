import { describe, expect, it } from "vitest";
import type { BusOption } from "../../types/bus";
import { accessibilityScore, getApproachThreshold } from "./BusInfoList";
import { selectRecordingMimeType } from "./VoiceRecording";

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
    congetion: 3,
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
    expect(accessibilityScore(bus({ congetion: 0 }))).toBeGreaterThan(
      accessibilityScore(bus({ congetion: 3 })),
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
