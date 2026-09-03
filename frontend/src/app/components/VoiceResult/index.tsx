import { useCallback, useEffect, useRef, useState } from "react";
import { Home, Info, MapPin, Mic, Play, RotateCcw, ShieldCheck, Square, Volume2 } from "lucide-react";
import type { SafetyDecision } from "../../../api/client";
import type { BusOption } from "../../../types/bus";
import { SPEECH_CANCEL_EVENT, applySpeechVolume, cancelSpeech, signalSpeechActivity, speakKorean } from "../../../utils/speech";
import { BusList } from "./BusList";
import { RouteDetailOverlay } from "./RouteDetail";

interface VoiceResultProps {
  destination?: string;
  buses?: BusOption[];
  message?: string;
  audioBase64?: string;
  audio_base64?: string;
  safetyDecision?: SafetyDecision | null;
  onReset: () => void;
  onGoHome: () => void;
}

// 가장 긴 안내 문장을 서버 음성으로 읽어도 넉넉한 값입니다.
const PLAYBACK_WATCHDOG_MS = 30_000;
const RAW_AUDIO_FALLBACK_WATCHDOG_MS = 60_000;
const RAW_AUDIO_END_GRACE_MS = 5_000;

function rawAudioWatchdogMs(audio: HTMLAudioElement): number {
  return Number.isFinite(audio.duration) && audio.duration > 0
    ? Math.ceil(audio.duration * 1_000) + RAW_AUDIO_END_GRACE_MS
    : RAW_AUDIO_FALLBACK_WATCHDOG_MS;
}

function formatCheckedAt(value?: string | null): string | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(timestamp);
}

export function VoiceResult({
  destination = "",
  buses = [],
  message = "",
  audioBase64 = "",
  audio_base64 = "",
  safetyDecision = null,
  onReset,
  onGoHome,
}: VoiceResultProps) {
  const [viewMode, setViewMode] = useState<"text" | "map">("text");
  const [selectedBus, setSelectedBus] = useState<BusOption | null>(buses[0] ?? null);
  const [playbackStatus, setPlaybackStatus] = useState<"idle" | "playing" | "blocked">("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const playbackIdRef = useRef(0);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rawAudioData = audio_base64 || audioBase64;
  const checkedAtLabel = formatCheckedAt(safetyDecision?.checked_at);

  // 재생 종료 신호가 오지 않아도 "재생 중" 표시에 갇히지 않게 하는 상한입니다.
  // 여기에 갇히면 소리도 나지 않고 대체 재생 버튼도 뜨지 않아, 이용자는 안내를
  // 들을 방법이 없어집니다. BusInfoList 의 도착 안내와 같은 보호입니다.
  const armPlaybackWatchdog = useCallback((playbackId: number, timeoutMs = PLAYBACK_WATCHDOG_MS) => {
    if (watchdogRef.current) clearTimeout(watchdogRef.current);
    watchdogRef.current = setTimeout(() => {
      if (playbackIdRef.current !== playbackId) return;
      const audio = audioRef.current;
      if (audio) {
        audio.onloadedmetadata = null;
        audio.onended = null;
        audio.onerror = null;
        audio.pause();
        audio.currentTime = 0;
        audioRef.current = null;
      }
      cancelSpeech();
      setPlaybackStatus((current) => (current === "playing" ? "blocked" : current));
    }, timeoutMs);
  }, []);

  const clearPlaybackWatchdog = useCallback(() => {
    if (watchdogRef.current) clearTimeout(watchdogRef.current);
    watchdogRef.current = null;
  }, []);

  useEffect(() => {
    setSelectedBus(buses[0] ?? null);
  }, [buses]);

  const stopRawPlayback = useCallback(() => {
    if (!audioRef.current) return;
    playbackIdRef.current += 1;
    clearPlaybackWatchdog();
    audioRef.current.onloadedmetadata = null;
    audioRef.current.onended = null;
    audioRef.current.onerror = null;
    audioRef.current.pause();
    audioRef.current.currentTime = 0;
    audioRef.current = null;
    setPlaybackStatus("idle");
  }, [clearPlaybackWatchdog]);

  const stopPlayback = useCallback(() => {
    // 서버 음성은 audioRef 를 쓰지 않으므로 stopRawPlayback 만으로는 이전 비동기
    // 결과가 무효화되지 않습니다. 새 안내가 시작될 때 항상 세대를 바꿉니다.
    playbackIdRef.current += 1;
    stopRawPlayback();
    clearPlaybackWatchdog();
    cancelSpeech();
    setPlaybackStatus("idle");
  }, [clearPlaybackWatchdog, stopRawPlayback]);

  useEffect(() => clearPlaybackWatchdog, [clearPlaybackWatchdog]);

  useEffect(() => {
    window.addEventListener(SPEECH_CANCEL_EVENT, stopRawPlayback);
    return () => window.removeEventListener(SPEECH_CANCEL_EVENT, stopRawPlayback);
  }, [stopRawPlayback]);

  const playMessage = useCallback(async () => {
    if (!message) return;
    stopPlayback();
    const playbackId = playbackIdRef.current;
    if (rawAudioData) {
      const audioUrl = rawAudioData.startsWith("data:")
        ? rawAudioData
        : `data:audio/wav;base64,${rawAudioData}`;
      const audio = applySpeechVolume(new Audio(audioUrl));
      audioRef.current = audio;
      audio.onloadedmetadata = () => {
        if (playbackIdRef.current !== playbackId || audioRef.current !== audio) return;
        armPlaybackWatchdog(playbackId, rawAudioWatchdogMs(audio));
      };
      audio.onended = () => {
        if (playbackIdRef.current !== playbackId) return;
        clearPlaybackWatchdog();
        audioRef.current = null;
        signalSpeechActivity();
        setPlaybackStatus("idle");
      };
      audio.onerror = () => {
        if (playbackIdRef.current !== playbackId) return;
        clearPlaybackWatchdog();
        audioRef.current = null;
        setPlaybackStatus("blocked");
      };
      try {
        await audio.play();
        if (playbackIdRef.current === playbackId && audioRef.current === audio) {
          setPlaybackStatus("playing");
          armPlaybackWatchdog(playbackId, rawAudioWatchdogMs(audio));
          signalSpeechActivity();
        }
      } catch {
        if (playbackIdRef.current === playbackId) setPlaybackStatus("blocked");
      }
    } else {
      // 브라우저가 한국어를 말할 수 없는 기기(라즈베리파이 등)에서는 서버 음성으로
      // 대체됩니다. 둘 다 안 되면 화면에 재생 버튼을 남깁니다.
      setPlaybackStatus("playing");
      let playbackEnded = false;
      const outcome = await speakKorean(message, {
        onEnd: () => {
          if (playbackIdRef.current !== playbackId) return;
          playbackEnded = true;
          clearPlaybackWatchdog();
          setPlaybackStatus("idle");
        },
      });
      if (
        playbackIdRef.current === playbackId
        && outcome === "browser"
        && !playbackEnded
      ) {
        // 브라우저 음성은 시작 후 Promise 가 바로 끝나므로 종료 이벤트 상실을
        // 별도로 감시합니다. 서버 음성은 자체적으로 실제 duration까지 기다립니다.
        armPlaybackWatchdog(playbackId);
      }
      if (
        playbackIdRef.current === playbackId
        && (outcome === "unavailable" || outcome === "partial")
      ) {
        clearPlaybackWatchdog();
        setPlaybackStatus("blocked");
      }
    }
  }, [armPlaybackWatchdog, clearPlaybackWatchdog, message, rawAudioData, stopPlayback]);

  useEffect(() => {
    if (!message) return;
    void playMessage();

    return stopPlayback;
  }, [message, playMessage, stopPlayback]);

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-[#123E49] font-kiosk">
      {/*
        안내 문구는 이 화면에서 소리로 재생됩니다. 같은 문장을 aria-live에도 넣으면
        스크린리더 낭독과 TTS가 겹쳐 두 번 들립니다. 그래서 본문에는 자동 낭독을
        일으키지 않는 sr-only 문단으로 두어 필요할 때 탐색해 읽을 수 있게 하고,
        소리 재생이 차단된 경우에만 aria-live로 알립니다.
      */}
      <p className="sr-only">{message}</p>
      <p aria-live="polite" className="sr-only">
        {playbackStatus === "blocked" ? message : ""}
      </p>

      <header className="z-10 flex min-h-14 shrink-0 items-center justify-between gap-2 border-b border-white/15 px-3 py-2 sm:px-5">
        <div className="flex min-w-0 items-center gap-2 sm:gap-4">
          <button type="button" onClick={onGoHome} className="icon-command" title="처음으로" aria-label="처음으로">
            <Home className="size-4" />
          </button>
          <div className="flex min-w-0 items-center gap-2 text-white">
            <MapPin className="size-5 shrink-0 text-[#F0C929]" />
            <strong title={`${destination || "목적지"} 방면`} className="truncate text-base sm:text-xl">{destination || "목적지"} 방면</strong>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {message && (
            <button type="button" onClick={() => void playMessage()} className="icon-command" title="음성 다시 듣기" aria-label="음성 다시 듣기"><RotateCcw className="size-4" /></button>
          )}
          {playbackStatus === "playing" && (
            <button type="button" onClick={stopPlayback} className="icon-command" title="음성 중지" aria-label="음성 중지"><Square className="size-4" /></button>
          )}
          <button type="button" onClick={onReset} title="다시 검색" aria-label="다시 검색" className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-md border border-white/20 bg-white/10 px-4 py-2 text-sm font-bold text-white hover:bg-white/20">
            <Mic className="size-4" aria-hidden="true" /><span className="hidden sm:inline">다시 검색</span>
          </button>
        </div>
      </header>

      {safetyDecision?.level === "verified" && (
        <details data-testid="route-safety-panel" className="shrink-0 border-b border-emerald-300/35 bg-[#0E333C] px-3 py-0.5 text-white sm:px-5 sm:py-2">
          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm font-black">
            <ShieldCheck className="size-4 shrink-0 text-emerald-300" />
            <span className="min-w-0 break-words">{safetyDecision.title}</span>
            <span className="ml-auto shrink-0 text-xs font-bold text-white/80">상세 보기</span>
          </summary>
          <ul className="mt-2 space-y-1 pl-5 text-sm leading-relaxed text-white/90">
            {safetyDecision.reasons.map((reason) => <li key={reason} className="list-disc">{reason}</li>)}
          </ul>
          {checkedAtLabel && <p className="mt-2 text-xs font-semibold text-white/80">교통 데이터 확인 {checkedAtLabel}</p>}
        </details>
      )}

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden sm:flex-row">
        {buses.length > 0 && <BusList buses={buses} selectedId={selectedBus?.id} onBusClick={setSelectedBus} />}
        <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden bg-white">
          {selectedBus?.routeDetail ? (
            <RouteDetailOverlay
              route={selectedBus.routeDetail}
              destination={destination}
              viewMode={viewMode}
              onToggleView={() => setViewMode((mode) => mode === "text" ? "map" : "text")}
            />
          ) : (
            <div className="grid h-full place-items-center bg-slate-50 px-5 text-center">
              <div className="max-w-xl rounded-xl border border-slate-200 bg-white px-6 py-7 shadow-sm">
                <Info className="mx-auto mb-3 size-9 text-[#145466]" />
                <h2 className="text-xl font-black text-slate-900">버스 운행 안내</h2>
                <p className="mt-3 text-base font-bold leading-relaxed text-slate-700">{message || "현재 표시할 수 있는 버스 도착 정보가 없습니다."}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/*
        아래 재생 패널에 role="status" 를 붙이면 안 됩니다. 암묵적 aria-live 라서,
        지금 소리로 재생 중인 바로 그 문장을 스크린리더가 한 번 더 읽어 두 번
        들립니다. 같은 문구는 위 sr-only 문단에 이미 있어 탐색해 읽을 수 있습니다.
        높이도 좁은 화면에서 더 조입니다. 이 패널이 커지면 경로 본문이 그만큼
        줄어드는데, 문구는 소리로도 나오지만 경로 단계 목록은 화면에만 있습니다.
      */}
      {playbackStatus === "playing" && message && (
        <div data-testid="playback-panel" className="flex max-h-14 shrink-0 items-start gap-3 border-t border-[#F0C929]/60 bg-[#171D23] px-4 py-2 text-white shadow-[0_-6px_18px_rgba(0,0,0,0.16)] sm:max-h-28 sm:items-center sm:py-3">
          <Volume2 className="size-5 shrink-0 text-[#F0C929]" />
          <p className="custom-scrollbar min-w-0 flex-1 overflow-y-auto text-sm font-bold leading-relaxed sm:text-base">{message}</p>
        </div>
      )}

      {playbackStatus === "blocked" && message && (
        <div data-testid="playback-panel" role="alert" className="flex shrink-0 items-center justify-between gap-3 border-t border-[#F0C929] bg-[#171D23] px-4 py-3 text-white shadow-[0_-6px_18px_rgba(0,0,0,0.16)]">
          <span className="flex min-w-0 items-center gap-2 text-sm font-bold"><Volume2 className="size-5 shrink-0 text-[#F0C929]" /> 음성 안내를 재생해 주세요.</span>
          <button type="button" onClick={() => void playMessage()} className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-md bg-[#F0C929] px-4 py-2 text-sm font-black text-[#171D23]"><Play className="size-4 fill-current" /> 재생</button>
        </div>
      )}
    </div>
  );
}
