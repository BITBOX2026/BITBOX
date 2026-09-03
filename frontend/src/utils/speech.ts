import { apiFetch, parseApiResponse } from "../api/client";
import { readKioskStorage, SPEECH_VOLUME_KEY, writeKioskStorage } from "./kioskStorage";
import { toSpokenKorean } from "./spokenKorean";

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

export type SpeechOutcome = "browser" | "server" | "partial" | "unavailable";
export type SpeechActivitySource = "session" | "background";
export const SPEECH_CANCEL_EVENT = "bitbox:speech-cancel";
/**
 * 안내 음성이 재생되기 시작했거나 끝났음을 알립니다.
 *
 * 공용 키오스크의 유휴 초기화는 화면 조작만 보고 있어서, 이용자가 안내를 듣는
 * 동안은 "아무것도 안 하는 중"으로 취급됐습니다. 듣는 것도 이용이므로 이 신호로
 * 유휴 시간을 다시 셉니다. 초기화 자체를 미루지는 않으므로 자리를 뜬 기기는
 * 그대로 90초 뒤 지워집니다.
 */
export const SPEECH_ACTIVITY_EVENT = "bitbox:speech-activity";

export function signalSpeechActivity(source: SpeechActivitySource = "session"): void {
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    window.dispatchEvent(new CustomEvent(SPEECH_ACTIVITY_EVENT, { detail: { source } }));
  }
}

const VOICE_LOOKUP_TIMEOUT_MS = 1_500;
// "한국어 음성 없음" 판정을 영구히 굳히지 않습니다. 기기 부팅 직후에는 음성
// 엔진 등록이 늦어 1.5초 안에 못 찾을 수 있는데, 그대로 캐시하면 재부팅 전까지
// 계속 서버 음성으로 우회하게 됩니다.
const VOICE_NEGATIVE_CACHE_MS = 5 * 60 * 1_000;
// 서버 음성 요청 상한. 이 값이 없으면 응답이 늦는 동안 화면이 "재생 중"에
// 묶인 채 소리도 대체 버튼도 나오지 않습니다.
// 백엔드 TTS 상한(기본 15초)이 먼저 끝나고 503/무음 응답을 돌려줄 수 있도록
// 네트워크 여유 2초를 둡니다. 클라이언트가 먼저 끊어 유료 작업만 남기지 않습니다.
const SERVER_SPEECH_TIMEOUT_MS = 17_000;
// 서버 /api/speech 가 받아 주는 문장 길이(MAX_SPEECH_CHARS)와 같아야 합니다.
// 넘으면 422 로 거절당해 안내가 통째로 무음이 됩니다.
const SERVER_SPEECH_MAX_CHARS = 200;
// 재생 Promise 가 성공한 뒤 ended/error 이벤트가 사라지는 Chromium·오디오 장치
// 장애에서도 다음 안내를 영구히 막지 않습니다. 정상 오디오의 duration 을 읽으면
// 실제 길이에 여유를 더한 값으로 다시 계산합니다.
const SERVER_AUDIO_FALLBACK_TIMEOUT_MS = 60_000;
const SERVER_AUDIO_END_GRACE_MS = 5_000;
// speak() 직후 재생이 실제로 시작됐는지 지켜보는 창. 리눅스 Chromium 은
// 음성이 있는데도 소리 없이 끝나거나 error 로 끝나는 사례가 있습니다.
const BROWSER_SPEECH_START_MS = 1_200;
// 청력이 떨어진 이용자를 위해 보통보다 15% 느리게 읽습니다. 서버 TTS(TTS_SPEED)와
// 같은 값이어야 기기에 한국어 음성이 있고 없고에 따라 말 속도가 달라지지 않습니다.
// 이보다 더 늦추면 억양이 뭉개져 오히려 알아듣기 어려워집니다.
// 브라우저 음성 속도입니다.
//
// 서버 음성은 배속을 걷어내고 말투 지시로 "또박또박, 천천히" 를 맡깁니다. 여기만
// 0.85 로 남겨 두면 기기에 한국어 음성이 있는지 없는지에 따라 같은 안내가 다른
// 속도로 들립니다. 배속을 크게 낮추면 또박또박이 아니라 늘어지게 들린다는 것이
// 이번에 서버 쪽에서 확인된 바라, 알아듣기 쉬운 만큼만 낮춥니다.
export const SPEECH_RATE = 0.95;

/**
 * 안내 음량입니다.
 *
 * 무인정보단말기 접근성 기준은 이용자가 음량을 조절할 수 있어야 한다고 요구합니다.
 * 정류장은 조용할 때도 있고 차 소리에 묻힐 때도 있어, 한 값으로 맞출 수 없습니다.
 *
 * 0(무음)은 넣지 않습니다. 화면을 보기 어려운 이용자에게 소리가 유일한 통로인데,
 * 앞사람이 꺼 둔 상태로 남으면 다음 사람은 아무 안내도 받지 못합니다.
 */
export const SPEECH_VOLUME_STEPS = [0.2, 0.4, 0.6, 0.8, 1] as const;
export const SPEECH_VOLUME_EVENT = "bitbox:speech-volume";

let speechVolume = readStoredVolume();

function readStoredVolume(): number {
  const stored = Number(readKioskStorage(SPEECH_VOLUME_KEY));
  if (!Number.isFinite(stored)) return 1;
  // 저장값이 손상돼도 들리는 쪽으로 되돌립니다.
  return SPEECH_VOLUME_STEPS.includes(stored as (typeof SPEECH_VOLUME_STEPS)[number])
    ? stored
    : 1;
}

export function getSpeechVolume(): number {
  return speechVolume;
}

/** 현재 음량이 몇 단계인지(1부터) 돌려줍니다. 화면 표시용입니다. */
export function getSpeechVolumeStep(): number {
  return SPEECH_VOLUME_STEPS.indexOf(speechVolume as (typeof SPEECH_VOLUME_STEPS)[number]) + 1;
}

/** 한 단계 올리거나 내립니다. 양 끝에서는 더 움직이지 않습니다. */
export function shiftSpeechVolume(direction: 1 | -1): number {
  const current = SPEECH_VOLUME_STEPS.indexOf(
    speechVolume as (typeof SPEECH_VOLUME_STEPS)[number],
  );
  const next = Math.min(
    SPEECH_VOLUME_STEPS.length - 1,
    Math.max(0, (current < 0 ? SPEECH_VOLUME_STEPS.length - 1 : current) + direction),
  );
  speechVolume = SPEECH_VOLUME_STEPS[next];
  writeKioskStorage(SPEECH_VOLUME_KEY, String(speechVolume));
  // 재생 중인 소리에도 바로 반영해야 이용자가 누른 결과를 즉시 듣습니다.
  // 끝난 오디오는 참조를 붙들지 않도록 이때 함께 정리합니다.
  for (const audio of livePlayback) {
    if (audio.ended) {
      livePlayback.delete(audio);
      continue;
    }
    audio.volume = speechVolume;
  }
  // 브라우저 speechSynthesis 는 표준상 재생 중 음량을 바꿀 수 없습니다. 이미 말하고
  // 있는 문장은 그대로 끝나고, 다음 안내부터 새 음량이 적용됩니다.
  //
  // 창 객체가 없는 환경(단위 테스트 등)에서도 음량 계산 자체는 동작해야 합니다.
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SPEECH_VOLUME_EVENT));
  }
  return speechVolume;
}

/**
 * 재생을 시작하기 직전의 오디오에 현재 음량을 걸고, 재생 중 목록에 올립니다.
 *
 * 안내 오디오는 세 곳에서 만들어집니다. 서버 대체 음성, 미리 받아 둔 경로 안내,
 * 장소 확인 질문입니다. 예전에는 이 중 서버 대체 음성만 추적해서, 다른 소리가
 * 나오는 동안 음량 버튼을 눌러도 그 소리에는 반영되지 않고 다음 안내부터
 * 적용됐습니다. 이용자는 누른 결과를 바로 듣지 못했습니다.
 */
const livePlayback = new Set<HTMLAudioElement>();

export function applySpeechVolume(audio: HTMLAudioElement): HTMLAudioElement {
  audio.volume = speechVolume;
  livePlayback.add(audio);
  const forget = () => livePlayback.delete(audio);
  audio.addEventListener("ended", forget);
  audio.addEventListener("error", forget);
  return audio;
}

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

/**
 * 안내 문장을 서버가 받아 주는 길이로 나눕니다.
 *
 * 환승이 두 번 있는 경로 안내는 236자까지 늘어나는데 `/api/speech` 는 200자를
 * 넘으면 422 로 거절합니다. 통째로 보내면 기기에 한국어 음성이 없는 키오스크에서
 * **경로가 복잡할수록 안내가 아예 들리지 않습니다.** 문장 단위로 끊어 순서대로
 * 읽으면 길이 제한을 넘지 않고, 반복되는 문장은 서버 캐시에 그대로 걸립니다.
 */
export function splitForSpeech(text: string, limit = SERVER_SPEECH_MAX_CHARS): string[] {
  const sentences = text.split(/(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean);
  const chunks: string[] = [];
  let current = "";

  for (const sentence of sentences) {
    // 한 문장이 그 자체로 상한을 넘는 경우는 안내 문구 구조상 없지만,
    // 넘더라도 거절당하지 않도록 잘라서 보냅니다.
    for (let index = 0; index < sentence.length; index += limit) {
      const piece = sentence.slice(index, index + limit);
      if (!current) {
        current = piece;
      } else if (current.length + 1 + piece.length <= limit) {
        current = `${current} ${piece}`;
      } else {
        chunks.push(current);
        current = piece;
      }
    }
  }

  if (current) chunks.push(current);
  return chunks;
}

/** 재생이 끝날 때까지 기다립니다. 취소되면 즉시 false 로 끝납니다. */
function playAudioToEnd(audio: HTMLAudioElement, generation: number): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    let timeoutId = window.setTimeout(() => finish(false), SERVER_AUDIO_FALLBACK_TIMEOUT_MS);
    const finish = (completed: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      window.removeEventListener(SPEECH_CANCEL_EVENT, onCancel);
      audio.onloadedmetadata = null;
      audio.onended = null;
      audio.onerror = null;
      if (!completed) {
        audio.pause();
        audio.currentTime = 0;
      }
      resolve(completed);
    };
    const onCancel = () => finish(false);
    window.addEventListener(SPEECH_CANCEL_EVENT, onCancel);
    audio.onloadedmetadata = () => {
      if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(
        () => finish(false),
        Math.ceil(audio.duration * 1_000) + SERVER_AUDIO_END_GRACE_MS,
      );
    };
    audio.onended = () => finish(true);
    audio.onerror = () => finish(false);
    audio.play().then(
      () => {
        if (speechGeneration !== generation) {
          audio.pause();
          finish(false);
        }
      },
      () => finish(false),
    );
  });
}

async function fetchSpeechAudio(text: string, generation: number): Promise<string | null> {
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
    if (speechGeneration !== generation || controller.signal.aborted) return null;
    return payload.audio_base64 || null;
  } catch {
    // 자동 재생 차단·네트워크 실패 등. 화면 안내는 그대로 남으므로 무음으로 처리합니다.
    return null;
  } finally {
    window.clearTimeout(timeoutId);
    if (activeRequest === controller) activeRequest = null;
  }
}

async function playServerSpeech(
  text: string,
  generation: number,
  onEnd?: () => void,
  activitySource: SpeechActivitySource = "session",
): Promise<SpeechOutcome> {
  const chunks = splitForSpeech(text);
  if (chunks.length === 0) return "unavailable";

  for (let index = 0; index < chunks.length; index += 1) {
    const audioBase64 = await fetchSpeechAudio(chunks[index], generation);
    if (speechGeneration !== generation) return "unavailable";
    // 뒤 조각이 실패해도 전체 안내를 완료한 것은 아닙니다. 부분 성공을 별도로
    // 알려 화면이 재생 완료로 오인하지 않고 다시 듣기 수단을 남기게 합니다.
    if (!audioBase64) return index === 0 ? "unavailable" : "partial";

    const audio = applySpeechVolume(new Audio(`data:audio/wav;base64,${audioBase64}`));
    activeAudio = audio;
    signalSpeechActivity(activitySource);

    const completed = await playAudioToEnd(audio, generation);
    if (activeAudio === audio) activeAudio = null;
    if (!completed || speechGeneration !== generation) {
      return index === 0 ? "unavailable" : "partial";
    }
  }

  signalSpeechActivity(activitySource);
  onEnd?.();
  return "server";
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
  onStarted: () => void,
): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (started: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      resolve(started);
    };
    utterance.onstart = () => {
      if (settled) return;
      onStarted();
      finish(true);
    };
    utterance.onerror = () => finish(false);
    // 음성 객체가 있어도 출력과 이벤트가 모두 사라지는 Chromium 구성이 있습니다.
    // 시작을 확인하지 못하면 성공으로 꾸미지 않고 서버 음성으로 대체합니다.
    const timer = window.setTimeout(() => finish(false), BROWSER_SPEECH_START_MS);
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
  options: {
    onEnd?: () => void;
    rate?: number;
    activitySource?: SpeechActivitySource;
  } = {},
): Promise<SpeechOutcome> {
  const message = text.trim();
  if (!message) return "unavailable";
  // 화면 문구와 읽는 문구를 분리합니다. 화면은 `3412번`을 그대로 보여 주고,
  // 소리로는 정류장 안내처럼 `삼사일이 번`으로 또박또박 읽습니다.
  const spoken = toSpokenKorean(message);

  cancelSpeech();
  const generation = speechGeneration;

  const voice = await resolveKoreanVoice();
  if (speechGeneration !== generation) return "unavailable";
  const speech = synthesis();
  if (voice && speech) {
    let browserStarted = false;
    const utterance = new SpeechSynthesisUtterance(spoken);
    utterance.lang = "ko-KR";
    utterance.rate = options.rate ?? SPEECH_RATE;
    utterance.volume = speechVolume;
    utterance.voice = voice;
    utterance.onend = () => {
      if (!browserStarted || speechGeneration !== generation) return;
      signalSpeechActivity(options.activitySource);
      options.onEnd?.();
    };
    const started = await speakWithBrowser(utterance, speech, () => {
      browserStarted = true;
    });
    if (speechGeneration !== generation) return "unavailable";
    if (started) {
      signalSpeechActivity(options.activitySource);
      return "browser";
    }

    // 브라우저 음성이 실패했습니다. 이 기기는 말할 수 없다고 보고 서버 음성으로
    // 넘깁니다. 판정을 다시 하도록 캐시도 비웁니다.
    rememberVoice(null);
    utterance.onstart = null;
    utterance.onend = null;
    utterance.onerror = null;
    speech.cancel();
  }

  return playServerSpeech(
    spoken,
    generation,
    options.onEnd,
    options.activitySource,
  );
}
