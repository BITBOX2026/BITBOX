import { describe, expect, it } from "vitest";
import { splitForSpeech } from "./speech";

/**
 * 서버 `/api/speech` 는 200자를 넘으면 422 로 거절합니다. 환승이 두 번 있는 경로
 * 안내는 236자까지 늘어나므로, 통째로 보내면 기기에 한국어 음성이 없는 키오스크에서
 * **경로가 복잡할수록 안내가 아예 들리지 않습니다.** 나눠 보내는 규칙을 고정합니다.
 */

// 실제 build_user_message 가 만드는 환승 2회 안내와 같은 구조·길이입니다.
const TWO_TRANSFER_GUIDANCE = [
  "한국체육대학교입구까지 약 4분 걸어가세요.",
  "한국체육대학교입구에서 3412번 버스를 타고 잠실종합운동장사거리에 내리세요.",
  "종합운동장역까지 약 4분 걸어가세요.",
  "종합운동장역에서 301번 버스를 타고 강남역사거리에 내리세요.",
  "강남역 2번 출구까지 약 3분 걸어가세요.",
  "강남역 2번 출구에서 146번 버스를 타고 신논현역에 내리세요.",
  "약 60분 소요되며, 요금은 2,500원입니다.",
].join(" ");

describe("splitForSpeech", () => {
  it("환승이 많은 안내도 서버 한도를 넘지 않게 나눈다", () => {
    expect(TWO_TRANSFER_GUIDANCE.length).toBeGreaterThan(200);
    const chunks = splitForSpeech(TWO_TRANSFER_GUIDANCE);
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(200);
    }
  });

  it("안내 내용을 빠뜨리지 않는다", () => {
    const chunks = splitForSpeech(TWO_TRANSFER_GUIDANCE);
    // 각 탑승 지시가 어느 조각에든 남아 있어야 합니다.
    for (const bus of ["3412번", "301번", "146번", "2,500원"]) {
      expect(chunks.some((chunk) => chunk.includes(bus))).toBe(true);
    }
  });

  it("짧은 안내는 나누지 않아 캐시 적중률을 지킨다", () => {
    const short = "3412번 버스가 곧 도착합니다. 승차를 준비해 주세요.";
    expect(splitForSpeech(short)).toEqual([short]);
  });

  it("문장 하나가 상한을 넘어도 거절당하지 않게 자른다", () => {
    const chunks = splitForSpeech(`${"가".repeat(450)}.`);
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(200);
    }
  });

  it("빈 문장은 조각을 만들지 않는다", () => {
    expect(splitForSpeech("   ")).toEqual([]);
  });
});
