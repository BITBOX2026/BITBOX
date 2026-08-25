import { afterEach, describe, expect, it, vi } from "vitest";
import { resetSpeechCapability, resolveKoreanVoice } from "./speech";

/**
 * 기기가 한국어를 말할 수 있는지 판정하는 부분만 검사합니다.
 *
 * 실제 재생(브라우저 음성 vs 서버 음성 대체)은 진짜 브라우저가 필요하므로
 * e2e (`renders spoken guidance ...`)에서 확인합니다.
 */

type VoiceLike = { lang: string; name: string };

function installSpeechSynthesis(voices: VoiceLike[], options: { lateVoices?: VoiceLike[] } = {}) {
  const listeners: Array<() => void> = [];
  let current = voices;
  const speech = {
    getVoices: () => current,
    addEventListener: (_type: string, handler: () => void) => listeners.push(handler),
    removeEventListener: () => {},
    cancel: () => {},
    speak: () => {},
  };
  vi.stubGlobal("window", {
    speechSynthesis: speech,
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
  });
  vi.stubGlobal("SpeechSynthesisUtterance", class {});
  return {
    emitLateVoices() {
      current = options.lateVoices ?? [];
      listeners.forEach((handler) => handler());
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSpeechCapability();
});

describe("resolveKoreanVoice", () => {
  it("finds an installed Korean voice", async () => {
    installSpeechSynthesis([{ lang: "en-US", name: "English" }, { lang: "ko-KR", name: "Korean" }]);
    const voice = await resolveKoreanVoice(50);
    expect(voice?.lang).toBe("ko-KR");
  });

  it("reports none when the device has no Korean voice", async () => {
    // 라즈베리파이 등 음성 엔진이 없는 기기: getVoices() 가 계속 비어 있고
    // voiceschanged 이벤트도 오지 않습니다. 무한 대기하면 안 됩니다.
    installSpeechSynthesis([]);
    const started = Date.now();
    const voice = await resolveKoreanVoice(50);
    expect(voice).toBeNull();
    expect(Date.now() - started).toBeLessThan(2_000);
  });

  it("ignores non-Korean voices even when several are installed", async () => {
    installSpeechSynthesis([
      { lang: "en-US", name: "English" },
      { lang: "ja-JP", name: "Japanese" },
    ]);
    expect(await resolveKoreanVoice(50)).toBeNull();
  });

  it("picks up voices that arrive after the first query", async () => {
    // Chrome 은 처음에 빈 배열을 주고 나중에 voiceschanged 로 채웁니다.
    const controller = installSpeechSynthesis([], { lateVoices: [{ lang: "ko-KR", name: "Korean" }] });
    const pending = resolveKoreanVoice(1_000);
    controller.emitLateVoices();
    expect((await pending)?.lang).toBe("ko-KR");
  });

  it("reports none when the browser has no speech synthesis at all", async () => {
    vi.stubGlobal("window", { setTimeout: globalThis.setTimeout.bind(globalThis) });
    expect(await resolveKoreanVoice(50)).toBeNull();
  });
});
