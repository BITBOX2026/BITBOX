import { afterEach, describe, expect, it, vi } from "vitest";
import {
  applySpeechVolume,
  getSpeechVolume,
  resetSpeechCapability,
  resolveKoreanVoice,
  shiftSpeechVolume,
} from "./speech";

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
  // setSystemTime 으로 옮긴 시계가 다음 테스트에 남지 않도록 되돌립니다.
  vi.useRealTimers();
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

  it("rechecks a negative result instead of deciding once for the whole uptime", async () => {
    // 기기 부팅 직후에는 음성 엔진 등록이 늦어 처음 조회에서 못 찾을 수 있습니다.
    // 그 결론을 영구히 굳히면 재부팅 전까지 계속 서버 음성으로 우회하게 됩니다.
    installSpeechSynthesis([]);
    expect(await resolveKoreanVoice(20)).toBeNull();

    installSpeechSynthesis([{ lang: "ko-KR", name: "Korean" }]);
    vi.setSystemTime(Date.now() + 10 * 60 * 1_000);
    expect((await resolveKoreanVoice(20))?.lang).toBe("ko-KR");
  });
});

describe("안내 음량", () => {
  /** 재생 중인 오디오를 흉내 냅니다. 음량만 바뀌면 되므로 최소한만 갖춥니다. */
  function fakeAudio(ended = false) {
    const listeners: Record<string, Array<() => void>> = {};
    return {
      volume: 1,
      ended,
      addEventListener(type: string, fn: () => void) {
        (listeners[type] ??= []).push(fn);
      },
      fire(type: string) {
        (listeners[type] ?? []).forEach((fn) => fn());
      },
    } as unknown as HTMLAudioElement & { fire(type: string): void };
  }

  it("재생 중인 오디오 전부에 즉시 반영한다", () => {
    // 안내 오디오는 서버 대체 음성·미리 받아 둔 경로 안내·장소 확인 질문 세 곳에서
    // 만들어집니다. 예전에는 서버 대체 음성만 추적해서, 다른 소리가 나오는 동안
    // 음량 버튼을 눌러도 그 소리에는 반영되지 않았습니다.
    const routeAudio = fakeAudio();
    const confirmAudio = fakeAudio();
    applySpeechVolume(routeAudio);
    applySpeechVolume(confirmAudio);

    shiftSpeechVolume(-1);

    expect(routeAudio.volume).toBe(getSpeechVolume());
    expect(confirmAudio.volume).toBe(getSpeechVolume());
    expect(getSpeechVolume()).toBeLessThan(1);
  });

  it("끝난 오디오는 더 붙들지 않는다", () => {
    const finished = fakeAudio();
    applySpeechVolume(finished);
    finished.fire("ended");
    const before = finished.volume;

    shiftSpeechVolume(-1);

    expect(finished.volume).toBe(before);
  });

  it("무음 단계로는 내려가지 않는다", () => {
    // 화면을 보기 어려운 이용자에게 소리가 유일한 통로입니다. 앞사람이 꺼 둔 채로
    // 남으면 다음 사람이 아무 안내도 받지 못합니다.
    for (let i = 0; i < 10; i += 1) shiftSpeechVolume(-1);
    expect(getSpeechVolume()).toBeGreaterThan(0);
  });
});
