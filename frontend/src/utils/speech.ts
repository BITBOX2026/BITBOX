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
// "한국어 음성 없음" 판정을 영구히 굳히지 않습니다. 기기 부팅 직후에는 음성
// 엔진 등록이 늦어 1.5초 안에 못 찾을 수 있는데, 그대로 캐시하면 재부팅 전까지
// 계속 서버 음성으로 우회하게 됩니다.
const VOICE_NEGATIVE_CACHE_MS = 5 * 60 * 1_000;
// 서버 음성 요청 상한. 이 값이 없으면 응답이 늦는 동안 화면이 "재생 중"에
// 묶인 채 소리도 대체 버튼도 나오지 않습니다.
const SERVER_SPEECH_TIMEOUT_MS = 12_000;
// speak() 직후 재생이 실제로 시작됐는지 지켜보는 창. 리눅스 Chromium 은
// 음성이 있는데도 소리 없이 끝나거나 error 로 끝나는 사례가 있습니다.
const BROWSER_SPEECH_START_MS = 1_200;

let cachedKoreanVoice: SpeechSynthesisVoice | null | undefined;
let cachedKoreanVoiceAt = 0;
let activeAudio: HTMLAudioElement | null = null;
let activeRequest: AbortController | null = null;
let speechGeneration = 0;

// 시계가 뒤로 점프해도 결과는 "음성을 한 번 더 찾아본다" 뿐이라 Date 로 충분합니다.
function now(): number {
  return Date.now();
}

function synthesis(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window
    ? window.speechSynthesis
    : null;
}

function findKoreanVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  return voices.find((voice) => voice.lang?.toLowerCase().startsWith("ko")) ?? null;
}

function rememberVoice(voice: SpeechSynthesisVoice | null): SpeechSynthesisVoice | null {
  cachedKoreanVoice = voice;
  cachedKoreanVoiceAt = now();
  return voice;
}

/**
 * 사용 가능한 한국어 voice 를 찾습니다.
 *
 * `getVoices()` 는 처음에 빈 배열을 돌려주고 나중에 `voiceschanged` 로 채워지는
 * 브라우저가 있어 잠깐 기다립니다. 음성 엔진이 아예 없는 기기에서는 이벤트가 영영
 * 오지 않으므로 반드시 시간 제한을 둡니다.
 */
export function resolveKoreanVoice(timeoutMs = VOICE_LOOKUP_TIMEOUT_MS): Promise<SpeechSynthesisVoice | null> {
  // 찾은 음성은 계속 씁니다. 못 찾았다는 결론만 일정 시간 뒤 다시 확인합니다.
  if (cachedKoreanVoice) return Promise.resolve(cachedKoreanVoice);
  if (
    cachedKoreanVoice === null
    && now() - cachedKoreanVoiceAt < VOICE_NEGATIVE_CACHE_MS
  ) {
    return Promise.resolve(null);
  }

  const speech = synthesis();
  // 일부 환경은 speechSynthesis 를 부분적으로만 구현합니다. getVoices 가 없으면
  // 어떤 음성이 있는지 알 수 없으므로 "말할 수 없음"으로 간주하고 서버로 넘깁니다.
  if (!speech || typeof speech.getVoices !== "function" || typeof SpeechSynthesisUtterance === "undefined") {
    return Promise.resolve(rememberVoice(null));
  }

  const immediate = findKoreanVoice(speech.getVoices() || []);
  if (immediate) {
    return Promise.resolve(rememberVoice(immediate));
  }

  if (typeof speech.addEventListener !== "function") {
    return Promise.resolve(rememberVoice(null));
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (voice: SpeechSynthesisVoice | null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      speech.removeEventListener?.("voiceschanged", onVoicesChanged);
      resolve(rememberVoice(voice));
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
  cachedKoreanVoiceAt = 0;
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
  // 응답이 없을 때 화면이 "재생 중"에 갇히지 않도록 요청 자체에 상한을 둡니다.
  const timeoutId = window.setTimeout(() => controller.abort(), SERVER_SPEECH_TIMEOUT_MS);
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
    window.clearTimeout(timeoutId);
    if (activeRequest === controller) activeRequest = null;
  }
}

/**
 * 브라우저 음성이 실제로 재생을 시작했는지 확인합니다.
 *
 * 리눅스 Chromium 은 한국어 voice 가 등록돼 있어도 `speak()` 가 `error` 로 끝나거나
 * 아무 이벤트 없이 조용히 끝나는 사례가 있습니다. 이 경우를 잡아내지 못하면
 * 소리는 나지 않는데 화면은 재생 중으로 보입니다.
 */
function speakWithBrowser(
  utterance: SpeechSynthesisUtterance,
  speech: SpeechSynthesis,
): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (started: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      resolve(started);
    };
    utterance.onstart = () => finish(true);
    utterance.onerror = () => finish(false);
    // onstart 를 보내지 않는 엔진이 있어, 짧게 기다린 뒤에도 오류가 없으면
    // 재생이 시작된 것으로 봅니다.
    const timer = window.setTimeout(() => finish(true), BROWSER_SPEECH_START_MS);
    speech.speak(utterance);
  });
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
    const started = await speakWithBrowser(utterance, speech);
    if (speechGeneration !== generation) return "unavailable";
    if (started) return "browser";

    // 브라우저 음성이 실패했습니다. 이 기기는 말할 수 없다고 보고 서버 음성으로
    // 넘깁니다. 판정을 다시 하도록 캐시도 비웁니다.
    rememberVoice(null);
    speech.cancel();
  }

  return playServerSpeech(message, generation, options.onEnd);
}
