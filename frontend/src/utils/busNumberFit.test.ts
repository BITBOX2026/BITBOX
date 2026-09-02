import { describe, expect, it } from "vitest";
import { busNumberFontSize, busNumberWidthUnits } from "./busNumberFit";

describe("노선번호 크기 맞춤", () => {
  it("한글은 전각, 숫자는 반각에 가깝게 폭을 센다", () => {
    expect(busNumberWidthUnits("3412")).toBeCloseTo(2.4);
    expect(busNumberWidthUnits("하남")).toBeCloseTo(2);
    expect(busNumberWidthUnits("30-5하남")).toBeCloseTo(0.6 * 4 + 2);
  });

  it("빈 값에도 0으로 나누지 않는다", () => {
    expect(busNumberWidthUnits("")).toBe(1);
    expect(busNumberFontSize("", 2)).not.toContain("Infinity");
  });

  it("글자가 길수록 칸 대비 작은 크기를 고른다", () => {
    const short = Number(/(\d+\.\d+)cqi/.exec(busNumberFontSize("146", 2))![1]);
    const long = Number(/(\d+\.\d+)cqi/.exec(busNumberFontSize("30-5하남", 2))![1]);
    expect(long).toBeLessThan(short);
  });

  it("넓은 칸에서도 최대 크기를 넘지 않는다", () => {
    // min() 이라 컨테이너가 아무리 넓어도 maxRem 에서 멈춥니다.
    expect(busNumberFontSize("146", 2)).toBe("min(2rem, 51.11cqi)");
  });

  it("cqi 값이 100%를 넘지 않아 한 줄에 담긴다", () => {
    for (const busNumber of ["1", "146", "3412", "9401-1", "30-5하남", "M6405"]) {
      const cqi = Number(/(\d+\.\d+)cqi/.exec(busNumberFontSize(busNumber, 2))![1]);
      const units = busNumberWidthUnits(busNumber);
      // 글자수 × 글자폭 ≤ 컨테이너 폭(100cqi) 이어야 넘치지 않습니다.
      expect(cqi * units).toBeLessThanOrEqual(100);
    }
  });
});
