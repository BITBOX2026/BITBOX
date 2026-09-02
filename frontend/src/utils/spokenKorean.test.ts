import { describe, expect, it } from "vitest";
import { spellBusNumber, spellDigits, toSpokenKorean } from "./spokenKorean";

describe("노선번호 자릿수 읽기", () => {
  it("숫자를 자릿수 그대로 읽는다", () => {
    expect(spellDigits("3412")).toBe("삼사일이");
    expect(spellDigits("146")).toBe("일사육");
    expect(spellDigits("0")).toBe("공");
  });

  it("노선번호를 정류장 안내처럼 자릿수로 끊어 읽는다", () => {
    // "삼천사백십이 번"으로 읽으면 화면의 3412 와 즉시 연결되지 않습니다.
    expect(toSpokenKorean("3412번 버스가 곧 도착합니다.")).toBe("삼사일이 번 버스가 곧 도착합니다.");
    expect(toSpokenKorean("146번 버스를 타세요.")).toBe("일사육 번 버스를 타세요.");
  });

  it("가지번호의 하이픈은 '다시'로 읽는다", () => {
    expect(toSpokenKorean("9401-1번")).toBe("구사공일 다시 일 번");
    expect(toSpokenKorean("30-5하남번")).toBe("삼공 다시 오 하남 번");
  });

  it("영문 접두·접미가 있는 실제 노선도 빠뜨리지 않는다", () => {
    expect(spellBusNumber("M6405")).toBe("엠 육사공오");
    expect(toSpokenKorean("M6405번 버스가 곧 도착합니다.")).toBe(
      "엠 육사공오 번 버스가 곧 도착합니다.",
    );
    expect(toSpokenKorean("N13번 버스를 타세요.")).toBe("엔 일삼 번 버스를 타세요.");
    expect(toSpokenKorean("1311B광주번 버스")).toBe("일삼일일 비 광주 번 버스");
  });

  it("출구·승강장 번호를 버스 노선으로 오인하지 않는다", () => {
    expect(toSpokenKorean("강남역 12번 출구까지 걸어가세요.")).toBe(
      "강남역 12번 출구까지 걸어가세요.",
    );
    expect(toSpokenKorean("강남역12번출구에서 기다리세요.")).toBe(
      "강남역12번출구에서 기다리세요.",
    );
    expect(toSpokenKorean("2번 승강장으로 이동하세요.")).toBe("2번 승강장으로 이동하세요.");
  });

  it("짧은 숫자는 버스 문맥이 있을 때만 노선으로 읽는다", () => {
    expect(toSpokenKorean("51번 버스를 타세요.")).toBe("오일 번 버스를 타세요.");
    expect(toSpokenKorean("2번 버스가 곧 도착합니다.")).toBe("이 번 버스가 곧 도착합니다.");
    expect(toSpokenKorean("12번 출구에서 51번으로 갈아타세요.")).toBe(
      "12번 출구에서 오일 번으로 갈아타세요.",
    );
  });

  it("번이 붙지 않은 진짜 수는 건드리지 않는다", () => {
    // "삼십 분"을 "삼 공 분"으로 읽으면 오히려 알아듣기 어렵습니다.
    expect(toSpokenKorean("전체 30분이고 예상 1,500원입니다.")).toBe("전체 30분이고 예상 1,500원입니다.");
    expect(toSpokenKorean("강남역 2호선 방면")).toBe("강남역 2호선 방면");
    expect(toSpokenKorean("세 정거장 이내로 접근했습니다.")).toBe("세 정거장 이내로 접근했습니다.");
    expect(toSpokenKorean("3정거장 전입니다.")).toBe("3정거장 전입니다.");
  });

  it("요금처럼 자리구분 쉼표가 있는 수를 노선번호로 오인하지 않는다", () => {
    expect(toSpokenKorean("예상 1,500원입니다.")).toBe("예상 1,500원입니다.");
  });

  it("한 문장에 노선번호가 여러 개여도 모두 바꾼다", () => {
    expect(toSpokenKorean("3412번에서 146번으로 갈아타세요.")).toBe(
      "삼사일이 번에서 일사육 번으로 갈아타세요.",
    );
  });

  it("실제 도착 안내 문구를 그대로 처리한다", () => {
    expect(toSpokenKorean("3412번 버스가 한 정거장 전입니다.")).toBe(
      "삼사일이 번 버스가 한 정거장 전입니다.",
    );
  });
});
