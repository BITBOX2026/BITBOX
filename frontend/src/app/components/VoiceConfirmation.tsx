import { Check, MapPin, Mic, TrainFront, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { PlaceSuggestion, SafetyDecision, TransitConfirmation } from "../../api/client";
import { cancelSpeech, speakKorean, SPEECH_CANCEL_EVENT } from "../../utils/speech";

interface VoiceConfirmationProps {
  confirmation: TransitConfirmation;
  transcript: string;
  audioBase64: string;
  safetyDecision: SafetyDecision | null;
  onSelect: (place: PlaceSuggestion) => void;
  onRetry: () => void;
}

export function VoiceConfirmation({ confirmation, transcript, audioBase64, safetyDecision, onSelect, onRetry }: VoiceConfirmationProps) {
  const candidate = confirmation.candidate;
  const alternatives = confirmation.alternatives || [];
  const candidateRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const playbackIdRef = useRef(0);
  const [playbackBlocked, setPlaybackBlocked] = useState(false);

  const stopRawPrompt = useCallback(() => {
    playbackIdRef.current += 1;
    audioRef.current?.pause();
    audioRef.current = null;
  }, []);

  const stopPrompt = useCallback(() => {
    stopRawPrompt();
    cancelSpeech();
  }, [stopRawPrompt]);

  useEffect(() => {
    window.addEventListener(SPEECH_CANCEL_EVENT, stopRawPrompt);
    return () => window.removeEventListener(SPEECH_CANCEL_EVENT, stopRawPrompt);
  }, [stopRawPrompt]);

  const playPrompt = useCallback(async () => {
    stopPrompt();
    const playbackId = playbackIdRef.current;
    setPlaybackBlocked(false);
    if (audioBase64) {
      const source = audioBase64.startsWith("data:")
        ? audioBase64
        : `data:audio/wav;base64,${audioBase64}`;
      const audio = new Audio(source);
      audioRef.current = audio;
      try {
        await audio.play();
        if (playbackIdRef.current !== playbackId || audioRef.current !== audio) {
          audio.pause();
        }
        return;
      } catch {
        if (playbackIdRef.current === playbackId && audioRef.current === audio) {
          audioRef.current = null;
        }
      }
    }
    if (playbackIdRef.current !== playbackId) return;
    if (await speakKorean(confirmation.prompt) !== "unavailable") return;
    if (playbackIdRef.current === playbackId) setPlaybackBlocked(true);
  }, [audioBase64, confirmation.prompt, stopPrompt]);

  useEffect(() => {
    candidateRef.current?.focus();
    void playPrompt();
    return stopPrompt;
  }, [playPrompt, stopPrompt]);

  /*
    이 확인 단계는 화면 하단 음성 패널 안에 그려지는 인라인 영역이며 모달이 아닙니다.
    이전에는 `role="dialog" aria-modal="true"`를 선언했는데, 그러면 스크린리더가
    이 영역 바깥 전체 — 즉 실시간 버스 전광판 — 를 숨겨 버립니다. 확인 중에도
    전광판은 계속 유효한 정보이므로 숨기면 안 됩니다. 또한 배경을 실제로 막지
    않으면서 포커스만 가두면 키보드 이용자가 전광판에 접근할 수 없게 됩니다.
    따라서 이름이 붙은 그룹으로 선언하고, 초기 포커스만 후보 버튼에 둡니다.
  */
  return (
    <div ref={dialogRef} className="fade-enter min-w-0" role="group" aria-labelledby="place-confirmation-title">
      <p className="mb-1 text-xs font-extrabold text-[#F0C929]">장소 확인</p>
      <h2 id="place-confirmation-title" className="text-[clamp(22px,4vw,34px)] font-black leading-tight">
        {confirmation.prompt}
      </h2>
      {transcript && <p className="mt-2 text-sm text-white/65">“{transcript}”로 들었어요.</p>}
      {safetyDecision && (
        <div className="mt-3 max-w-[520px] rounded-md border border-cyan-200/25 bg-cyan-950/25 px-3 py-2 text-sm" role="status">
          <strong className="block text-cyan-100">{safetyDecision.title}</strong>
          <p className="mt-1 text-white/70">{safetyDecision.reasons.join(" ")}</p>
        </div>
      )}

      <button ref={candidateRef} type="button" onClick={() => onSelect(candidate)} className="mt-4 flex w-full max-w-[520px] items-center gap-3 rounded-lg border-2 border-[#F0C929] bg-white px-4 py-3 text-left text-slate-900 shadow-xl focus:outline-none focus:ring-4 focus:ring-[#F0C929]/45">
        {candidate.category_code === "SW8" ? <TrainFront className="size-6 shrink-0 text-[#145466]" /> : <MapPin className="size-6 shrink-0 text-[#145466]" />}
        <span className="min-w-0 flex-1">
          <strong className="block truncate text-base">{candidate.name}</strong>
          <span className="block truncate text-xs text-slate-500">{candidate.category || candidate.address}</span>
        </span>
        <Check className="size-5 shrink-0 text-emerald-600" />
      </button>

      {alternatives.length > 0 && (
        <div className="mt-3 flex max-w-[520px] flex-wrap gap-2" aria-label="다른 장소 후보">
          {alternatives.slice(0, 3).map((place) => (
            <button key={`${place.name}-${place.x}`} type="button" onClick={() => onSelect(place)} className="rounded-md bg-white/10 px-3 py-2 text-xs font-bold text-white hover:bg-white/20">
              {place.name}
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={() => void playPrompt()} className="inline-flex items-center gap-2 rounded-md border border-white/25 px-3 py-2 text-sm font-bold text-white/85 hover:bg-white/10">
          <Volume2 className="size-4" /> 질문 다시 듣기
        </button>
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-2 rounded-md border border-white/25 px-3 py-2 text-sm font-bold text-white/85 hover:bg-white/10">
          <Mic className="size-4" /> 다시 말하기
        </button>
      </div>
      {playbackBlocked && <p role="status" className="mt-2 text-xs font-bold text-amber-200">자동 재생이 차단됐습니다. 질문 다시 듣기를 눌러 주세요.</p>}
    </div>
  );
}
