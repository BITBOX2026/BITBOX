import { describe, expect, it } from "vitest";
import {
  classifyArrival,
  cleanBusNumber,
  describeArrivalStatus,
  getCongestionLabel,
  parseRemainingStops,
  toCongestion,
} from "./busService";

describe("parseRemainingStops", () => {
  it("parses common Seoul arrival message formats", () => {
    expect(parseRemainingStops("[3번째 전] 잠시후 도착")).toBe(3);
    expect(parseRemainingStops("2번째전")).toBe(2);
    expect(parseRemainingStops("1정거장 전")).toBe(1);
    expect(parseRemainingStops("곧 도착")).toBe(0);
  });

  it("returns -1 when no stop count is available", () => {
    expect(parseRemainingStops("운행 종료")).toBe(-1);
  });
});

describe("bus display values", () => {
  it("preserves Korean village-bus route names", () => {
    expect(cleanBusNumber("강동01")).toBe("강동01");
    expect(cleanBusNumber("송파02번")).toBe("송파02");
  });

  it("keeps unavailable congestion distinct from free seating", () => {
    expect(toCongestion(undefined)).toBe(0);
    expect(toCongestion("0")).toBe(0);
    expect(toCongestion("3")).toBe(3);
    expect(getCongestionLabel(0)).toBe("정보 없음");
  });
});

describe("classifyArrival", () => {
  it("keeps standby and terminal distinct from a real ETA", () => {
    expect(classifyArrival(null, "출발대기")).toBe("standby");
    expect(classifyArrival(null, "운행 종료")).toBe("terminal");
    expect(classifyArrival(null, "")).toBe("unknown");
    expect(classifyArrival(undefined, undefined)).toBe("unknown");
    expect(classifyArrival(0, "곧 도착")).toBe("live");
    expect(classifyArrival(4, "4분후[2번째 전]")).toBe("live");
  });

  it("prefers the provider reason over a present minute value", () => {
    // 제공기관이 이유를 명시하면 분 값이 있어도 그 이유가 우선입니다.
    expect(classifyArrival(0, "운행종료")).toBe("terminal");
  });

  it("describes each status in Korean for the display", () => {
    expect(describeArrivalStatus("standby")).toBe("출발 대기 중");
    expect(describeArrivalStatus("terminal")).toBe("운행 종료");
    expect(describeArrivalStatus("unknown")).toBe("도착정보 없음");
  });
});
