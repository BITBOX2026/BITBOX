import { useCallback, useEffect, useRef, useState } from "react";
import { Home, Info, MapPin, Mic, Play, RotateCcw, ShieldCheck, Square, Volume2 } from "lucide-react";
import type { SafetyDecision } from "../../../api/client";
import type { BusOption } from "../../../types/bus";
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
  const rawAudioData = audio_base64 || audioBase64;
  const checkedAtLabel = formatCheckedAt(safetyDecision?.checked_at);

  useEffect(() => {
    setSelectedBus(buses[0] ?? null);
  }, [buses]);

  const stopPlayback = useCallback(() => {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    audioRef.current = null;
    window.speechSynthesis?.cancel();
    setPlaybackStatus("idle");
  }, []);

  const playMessage = useCallback(async () => {
    if (!message) return;
    stopPlayback();
    if (rawAudioData) {
      const audioUrl = rawAudioData.startsWith("data:")
        ? rawAudioData
        : `data:audio/wav;base64,${rawAudioData}`;
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audio.onended = () => setPlaybackStatus("idle");
      audio.onerror = () => setPlaybackStatus("blocked");
      try {
        await audio.play();
        setPlaybackStatus("playing");
      } catch {
        setPlaybackStatus("blocked");
      }
    } else if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.lang = "ko-KR";
      utterance.rate = 0.9;
      utterance.onend = () => setPlaybackStatus("idle");
      utterance.onerror = () => setPlaybackStatus("blocked");
      setPlaybackStatus("playing");
      window.speechSynthesis.speak(utterance);
    }
  }, [message, rawAudioData, stopPlayback]);

  useEffect(() => {
    if (!message) return;
    void playMessage();

    return stopPlayback;
  }, [message, playMessage, stopPlayback]);

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-[#123E49] font-['Noto_Sans_KR']">
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
