import { describe, expect, it } from "vitest";
import { createVolumeReader } from "./useVoiceRecorder";

/**
 * 말소리 감지 감도를 지킵니다.
 *
 * `getByteFrequencyData` 는 `frequencyBinCount` 개만 채우고 나머지 칸은 건드리지
 * 않습니다. 버퍼를 `fftSize`(= frequencyBinCount * 2) 로 잡으면 뒤쪽 절반이 0 인
 * 채로 평균에 섞여 감도가 정확히 절반이 됩니다. 목소리가 작은 고령 이용자의
 * 발화를 놓치는 원인이라 회귀를 막습니다.
 */
function fakeAnalyser(fftSize: number, level: number) {
  const frequencyBinCount = fftSize / 2;
  return {
    frequencyBinCount,
    getByteFrequencyData(target: Uint8Array) {
      // 실제 구현과 같이 frequencyBinCount 개까지만 채웁니다.
      const fillable = Math.min(frequencyBinCount, target.length);
      for (let index = 0; index < fillable; index += 1) target[index] = level;
    },
  };
}

describe("createVolumeReader", () => {
  it("분석기가 채운 구간만으로 평균을 계산한다", () => {
    const read = createVolumeReader(fakeAnalyser(2048, 40));
    expect(read()).toBe(40);
  });

  it("fftSize 길이로 잡았을 때의 절반 값이 나오지 않는다", () => {
    const read = createVolumeReader(fakeAnalyser(2048, 40));
    // 버퍼를 fftSize 로 잡으면 20 이 됩니다. 그 회귀를 막습니다.
    expect(read()).not.toBe(20);
  });

  it("조용하면 0 을 돌려준다", () => {
    expect(createVolumeReader(fakeAnalyser(2048, 0))()).toBe(0);
  });

  it("분석 구간이 없어도 나눗셈이 깨지지 않는다", () => {
    expect(createVolumeReader(fakeAnalyser(0, 40))()).toBe(0);
  });
});
