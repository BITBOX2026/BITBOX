import { describe, expect, it } from "vitest";
import {
  cleanBusNumber,
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
