import { describe, expect, it } from "vitest";
import { readableTextColor } from "./VoiceResult/RouteDetail";

/** WCAG 2.x 상대 휘도 대비비 계산 (테스트 자체 구현 — 구현 코드와 독립) */
function contrastRatio(a: string, b: string): number {
  const luminance = (hex: string): number => {
    const raw = hex.replace("#", "");
    const channel = (offset: number): number => {
      const value = Number.parseInt(raw.slice(offset, offset + 2), 16) / 255;
      return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
  };
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

// RouteDetail 의 ROUTE_COLORS 와 도보 색상. 팔레트를 바꾸면 이 목록도 함께 갱신해야 합니다.
const ROUTE_COLORS = ["#0072B2", "#009E73", "#D55E00", "#CC79A7"];
const WALK_COLOR = "#64748B";

describe("지도 경로 라벨 대비", () => {
  it("모든 경로 색상이 선택된 글자색과 WCAG AA(4.5:1)를 만족한다", () => {
    for (const background of [...ROUTE_COLORS, WALK_COLOR]) {
      const foreground = readableTextColor(background);
      const ratio = contrastRatio(foreground, background);
      expect(
        ratio,
        `${background} 배경 + ${foreground} 글자 대비 ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("흰 글씨를 고정하면 대비 기준을 넘지 못하는 색이 있다 (회귀 방지 근거)", () => {
    const failing = ROUTE_COLORS.filter(
      (background) => contrastRatio("#FFFFFF", background) < 4.5,
    );
    // 과거 회귀: 라벨이 text-white 고정이라 3개 색이 미달이었습니다.
    expect(failing).toEqual(["#009E73", "#D55E00", "#CC79A7"]);
  });

  it("밝은 배경에는 검은 글씨, 어두운 배경에는 흰 글씨를 고른다", () => {
    expect(readableTextColor("#FFFFFF")).toBe("#000000");
    expect(readableTextColor("#000000")).toBe("#FFFFFF");
    expect(readableTextColor("#0072B2")).toBe("#FFFFFF");
    expect(readableTextColor("#CC79A7")).toBe("#000000");
  });

  it("형식이 잘못된 값에도 안전한 기본값을 돌려준다", () => {
    expect(readableTextColor("")).toBe("#000000");
    expect(readableTextColor("#fff")).toBe("#000000");
  });
});
