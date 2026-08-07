import { describe, expect, it } from "vitest";
import { parseRemainingStops } from "./busService";

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
