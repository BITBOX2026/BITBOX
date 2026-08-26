import { useCallback, useEffect, useRef, useState } from "react";
import { Home, Info, MapPin, Mic, Play, RotateCcw, ShieldCheck, Square, Volume2 } from "lucide-react";
import type { SafetyDecision } from "../../../api/client";
import type { BusOption } from "../../../types/bus";
import { cancelSpeech, signalSpeechActivity, speakKorean, SPEECH_CANCEL_EVENT } from "../../../utils/speech";
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
      const audio = new Audio(audioUrl);
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
            <strong className="truncate text-base sm:text-xl">{destination || "목적지"} 방면</strong>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {message && (
            <button type="button" onClick={() => void playMessage()} className="icon-command" title="음성 다시 듣기" aria-label="음성 다시 듣기"><RotateCcw className="size-4" /></button>
          )}
          {playbackStatus === "playing" && (
            <button type="button" onClick={stopPlayback} className="icon-command" title="음성 중지" aria-label="음성 중지"><Square className="size-4" /></button>
          )}
          <button type="button" onClick={onReset} title="다시 검색" aria-label="다시 검색" className="inline-flex shrink-0 items-center gap-2 rounded-md border border-white/20 bg-white/10 px-3 py-2 text-sm font-bold text-white hover:bg-white/20">
            <Mic className="size-4" aria-hidden="true" /><span className="hidden sm:inline">다시 검색</span>
          </button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden sm:flex-row">
        {buses.length > 0 && <BusList buses={buses} selectedId={selectedBus?.id} onBusClick={setSelectedBus} />}
        <div className="relative min-w-0 flex-1 bg-white">
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

      {safetyDecision?.level === "verified" && (
        <details className="absolute bottom-3 left-3 z-20 max-w-[min(440px,calc(100%-1.5rem))] rounded-md border border-emerald-300/60 bg-[#123E49]/95 px-3 py-2 text-white shadow-xl backdrop-blur-sm">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-black">
            <ShieldCheck className="size-4 text-emerald-300" /> {safetyDecision.title}
          </summary>
          <ul className="mt-2 space-y-1 pl-5 text-xs leading-relaxed text-white/80">
            {safetyDecision.reasons.map((reason) => <li key={reason} className="list-disc">{reason}</li>)}
          </ul>
          {checkedAtLabel && <p className="mt-2 text-[11px] font-semibold text-white/60">교통 데이터 확인 {checkedAtLabel}</p>}
        </details>
      )}

      {playbackStatus === "playing" && message && (
        <div className="absolute bottom-3 left-1/2 z-[999] flex w-[calc(100%-1.5rem)] max-w-[680px] -translate-x-1/2 items-center gap-3 rounded-md border border-[#F0C929]/60 bg-[#171D23]/95 px-4 py-3 text-white shadow-2xl backdrop-blur-sm">
          <Volume2 className="size-5 shrink-0 text-[#F0C929]" />
          <p className="min-w-0 text-sm font-bold leading-relaxed sm:text-base">{message}</p>
        </div>
      )}

      {playbackStatus === "blocked" && message && (
        <div className="absolute bottom-3 left-1/2 z-[999] flex w-[calc(100%-1.5rem)] max-w-[520px] -translate-x-1/2 items-center justify-between gap-3 rounded-md border border-[#F0C929] bg-[#171D23] px-4 py-3 text-white shadow-2xl">
          <span className="flex min-w-0 items-center gap-2 text-sm font-bold"><Volume2 className="size-5 shrink-0 text-[#F0C929]" /> 음성 안내를 재생해 주세요.</span>
          <button type="button" onClick={() => void playMessage()} className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[#F0C929] px-3 py-2 text-sm font-black text-[#171D23]"><Play className="size-4 fill-current" /> 재생</button>
        </div>
      )}
    </div>
  );
}
