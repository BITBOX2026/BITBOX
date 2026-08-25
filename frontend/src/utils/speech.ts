import { apiFetch, parseApiResponse } from "../api/client";

/**
 * 한국어 음성 안내 출력.
 *
 * 브라우저의 `speechSynthesis` 는 기기에 음성 엔진이 설치돼 있을 때만 소리를 냅니다.
 * 라즈베리파이 같은 최소 설치 리눅스의 Chromium 은 한국어 voice 가 없는 경우가 많고,
 * 그때 `speak()` 는 **오류 없이 조용히 아무 일도 하지 않습니다**. 화면상으로는 정상이라
 * 무음인 것을 알아채기 어렵습니다.
 *
 * 교통약자용 키오스크에서 도착 안내가 들리지 않는 것은 핵심 기능 상실이므로,
 * 브라우저가 한국어를 말할 수 없으면 서버 음성 합성(`POST /api/speech`)으로 대체합니다.
 * 서버 합성은 브라우저가 말할 수 있는 기기에서는 호출되지 않으므로 비용이 늘지 않습니다.
 */

export type SpeechOutcome = "browser" | "server" | "unavailable";
export const SPEECH_CANCEL_EVENT = "bitbox:speech-cancel";

const VOICE_LOOKUP_TIMEOUT_MS = 1_500;

let cachedKoreanVoice: SpeechSynthesisVoice | null | undefined;
let activeAudio: HTMLAudioElement | null = null;
let activeRequest: AbortController | null = null;
let speechGeneration = 0;

function synthesis(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window
    ? window.speechSynthesis
    : null;
}

function findKoreanVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  return voices.find((voice) => voice.lang?.toLowerCase().startsWith("ko")) ?? null;
}

/**
 * 사용 가능한 한국어 voice 를 찾습니다.
 *
 * `getVoices()` 는 처음에 빈 배열을 돌려주고 나중에 `voiceschanged` 로 채워지는
 * 브라우저가 있어 잠깐 기다립니다. 음성 엔진이 아예 없는 기기에서는 이벤트가 영영
 * 오지 않으므로 반드시 시간 제한을 둡니다.
 */
export function resolveKoreanVoice(timeoutMs = VOICE_LOOKUP_TIMEOUT_MS): Promise<SpeechSynthesisVoice | null> {
  if (cachedKoreanVoice !== undefined) return Promise.resolve(cachedKoreanVoice);

  const speech = synthesis();
  // 일부 환경은 speechSynthesis 를 부분적으로만 구현합니다. getVoices 가 없으면
  // 어떤 음성이 있는지 알 수 없으므로 "말할 수 없음"으로 간주하고 서버로 넘깁니다.
  if (!speech || typeof speech.getVoices !== "function" || typeof SpeechSynthesisUtterance === "undefined") {
    cachedKoreanVoice = null;
    return Promise.resolve(null);
  }

  const immediate = findKoreanVoice(speech.getVoices() || []);
  if (immediate) {
    cachedKoreanVoice = immediate;
    return Promise.resolve(immediate);
  }

  if (typeof speech.addEventListener !== "function") {
    cachedKoreanVoice = null;
    return Promise.resolve(null);
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (voice: SpeechSynthesisVoice | null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      speech.removeEventListener?.("voiceschanged", onVoicesChanged);
      cachedKoreanVoice = voice;
      resolve(voice);
    };
    const onVoicesChanged = () => {
      const voice = findKoreanVoice(speech.getVoices() || []);
      if (voice) finish(voice);
    };
    const timer = window.setTimeout(() => finish(findKoreanVoice(speech.getVoices() || [])), timeoutMs);
    speech.addEventListener?.("voiceschanged", onVoicesChanged);
  });
}

/** 테스트에서 기기 능력이 바뀐 상황을 재현하기 위해 캐시를 비웁니다. */
export function resetSpeechCapability(): void {
  cachedKoreanVoice = undefined;
}

/** 브라우저 음성과 서버 음성 재생을 모두 멈춥니다. */
export function cancelSpeech(): void {
  speechGeneration += 1;
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    window.dispatchEvent(new Event(SPEECH_CANCEL_EVENT));
  }
  activeRequest?.abort();
  activeRequest = null;
  synthesis()?.cancel();
  if (activeAudio) {
    activeAudio.onended = null;
    activeAudio.onerror = null;
    activeAudio.pause();
    activeAudio.currentTime = 0;
    activeAudio = null;
  }
}

async function playServerSpeech(
  text: string,
  generation: number,
  onEnd?: () => void,
): Promise<SpeechOutcome> {
  const controller = new AbortController();
  activeRequest = controller;
  try {
    const response = await apiFetch("/api/speech", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    const payload = await parseApiResponse<{ audio_base64?: string | null }>(
      response,
      "음성 안내를 준비하지 못했습니다.",
    );
    if (speechGeneration !== generation || controller.signal.aborted) return "unavailable";
    if (!payload.audio_base64) return "unavailable";

    const audio = new Audio(`data:audio/wav;base64,${payload.audio_base64}`);
    activeAudio = audio;
    audio.onended = () => {
      if (activeAudio !== audio || speechGeneration !== generation) return;
      activeAudio = null;
      onEnd?.();
    };
    await audio.play();
    if (speechGeneration !== generation || activeAudio !== audio) {
      audio.pause();
      return "unavailable";
    }
    return "server";
  } catch {
    // 자동 재생 차단·네트워크 실패 등. 화면 안내는 그대로 남으므로 무음으로 처리합니다.
    if (activeAudio && speechGeneration === generation) activeAudio = null;
    return "unavailable";
  } finally {
    if (activeRequest === controller) activeRequest = null;
  }
}

/**
 * 문장을 소리로 읽습니다.
 *
 * @returns 무엇으로 읽었는지. `"unavailable"` 이면 소리가 나지 않았으므로
 *          호출자는 화면에 재생 버튼 같은 대안을 보여 주어야 합니다.
 */
export async function speakKorean(
  text: string,
  options: { onEnd?: () => void; rate?: number } = {},
): Promise<SpeechOutcome> {
  const message = text.trim();
  if (!message) return "unavailable";

  cancelSpeech();
  const generation = speechGeneration;

  const voice = await resolveKoreanVoice();
  if (speechGeneration !== generation) return "unavailable";
  const speech = synthesis();
  if (voice && speech) {
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.lang = "ko-KR";
    utterance.rate = options.rate ?? 0.9;
    utterance.voice = voice;
    utterance.onend = () => {
      if (speechGeneration === generation) options.onEnd?.();
    };
    speech.speak(utterance);
    return "browser";
  }

  return playServerSpeech(message, generation, options.onEnd);
}
