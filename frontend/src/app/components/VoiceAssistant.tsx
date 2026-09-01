import { AlertCircle, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { DestinationSearch } from "./DestinationSearch";
import { PrivacyNotice } from "./PrivacyNotice";
import { VoiceLoading } from "./VoiceLoading";
import { VoiceMicButton } from "./VoiceMicButton";
import { VoiceRecording } from "./VoiceRecording";
import { VoiceResult } from "./VoiceResult";
import { VoiceConfirmation } from "./VoiceConfirmation";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";
import { SPEECH_ACTIVITY_EVENT } from "../../utils/speech";
import {
  clearRecentDestinationHistory,
  readKioskStorage,
  removeKioskStorage,
  VOICE_CONSENT_KEY,
  writeKioskStorage,
} from "../../utils/kioskStorage";

interface VoiceAssistantProps {
  onResultModeChange?: (isResult: boolean) => void;
}

// 공용 키오스크에서 이전 이용자의 흔적이 남는 시간입니다. 개인정보 보장이므로
// 늘리지 않습니다. 대신 "무엇이 유휴인가"를 정확히 셉니다 — 안내를 듣는 중이거나
// 요청이 진행 중인 것은 유휴가 아닙니다.
const KIOSK_IDLE_RESET_MS = 90_000;
// 마이크·조회가 진행 중인 상태. 이용자가 화면을 만지지 않는 것이 정상이므로
// 유휴로 보고 세션을 지우면 안 됩니다. 각 상태는 자체 상한이 있어 멈추지 않습니다.
const ACTIVE_STATUSES = new Set(["starting", "listening", "loading"]);

export function VoiceAssistant({ onResultModeChange }: VoiceAssistantProps) {
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [consentRequired, setConsentRequired] = useState(false);
  // 저장소에 동의를 남기지 못한 기기를 위한 세션 한정 기억.
  // 세션이 끝날 때(홈·유휴 초기화) 반드시 함께 지웁니다.
  const sessionConsentRef = useRef(false);
  const {
    status,
    transcript,
    destination,
    buses,
    message,
    audioBase64,
    error,
    confirmation,
    safetyDecision,
    startRecording,
    stopRecording,
    submitTextRoute,
    confirmPlace,
    reset,
  } = useVoiceRecorder();

  const resetKioskSession = useCallback(() => {
    clearRecentDestinationHistory();
    removeKioskStorage(VOICE_CONSENT_KEY);
    sessionConsentRef.current = false;
    setPrivacyOpen(false);
    setConsentRequired(false);
    reset();
  }, [reset]);

  useEffect(() => {
    // 공용 키오스크에서는 브라우저 재시작 뒤 이전 이용자의 흔적을 복원하지 않습니다.
    // 동의도 함께 지웁니다. 화면이 다시 뜬 시점의 이용자는 직전 이용자와 다른
    // 사람일 수 있으므로, 이전 이용자의 동의로 새 이용자의 음성을 녹음하면 안 됩니다.
    clearRecentDestinationHistory();
    removeKioskStorage(VOICE_CONSENT_KEY);
  }, []);

  useEffect(() => {
    // 진행 중인 요청은 스스로 끝나므로(마이크·업로드 모두 상한이 있습니다)
    // 그동안은 유휴 타이머를 멈춰 둡니다.
    if (ACTIVE_STATUSES.has(status)) return;

    let timer = window.setTimeout(resetKioskSession, KIOSK_IDLE_RESET_MS);
    const rearm = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(resetKioskSession, KIOSK_IDLE_RESET_MS);
    };
    const rearmForSpeech = (event: Event) => {
      const source = event instanceof CustomEvent
        ? (event.detail as { source?: string } | null)?.source
        : undefined;
      // 전광판의 추적 버스 안내는 사용자의 경로 화면 조작이 아닙니다. 이를 활동으로
      // 세면 자리를 떠난 뒤에도 이전 목적지가 90초보다 오래 남을 수 있습니다.
      if (source === "background") return;
      rearm();
    };
    window.addEventListener("pointerdown", rearm);
    window.addEventListener("keydown", rearm);
    // 안내를 듣는 것도 이용입니다. 화면을 만지지 않았다는 이유로 낭독 도중
    // 결과가 사라지면 안 됩니다.
    window.addEventListener(SPEECH_ACTIVITY_EVENT, rearmForSpeech);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointerdown", rearm);
      window.removeEventListener("keydown", rearm);
      window.removeEventListener(SPEECH_ACTIVITY_EVENT, rearmForSpeech);
    };
  }, [resetKioskSession, status]);

  useEffect(() => {
    onResultModeChange?.(status === "result");
  }, [onResultModeChange, status]);

  const requestRecording = () => {
    // 저장소가 막힌 기기에서는 동의가 남지 않습니다. 그대로 두면 이용할 때마다
    // 개인정보 안내가 다시 떠서 사실상 음성 기능을 쓸 수 없게 됩니다.
    // 이 세션 안에서 받은 동의는 화면 상태로 기억합니다.
    if (!sessionConsentRef.current && readKioskStorage(VOICE_CONSENT_KEY) !== "accepted") {
      setConsentRequired(true);
      setPrivacyOpen(true);
      return;
    }
    void startRecording();
  };

  const toggleRecording = () => {
    if (status === "idle") requestRecording();
    if (status === "listening") stopRecording();
  };

  const acceptVoiceProcessing = () => {
    writeKioskStorage(VOICE_CONSENT_KEY, "accepted");
    sessionConsentRef.current = true;
    setPrivacyOpen(false);
    setConsentRequired(false);
    void startRecording();
  };

  if (status === "result") {
    return (
      <section className="relative h-full w-full">
        <VoiceResult
          destination={destination}
          buses={buses}
          message={message}
          safetyDecision={safetyDecision}
          audio_base64={audioBase64}
          onReset={requestRecording}
          onGoHome={resetKioskSession}
        />
        <PrivacyNotice open={privacyOpen} consentRequired={consentRequired} onAccept={acceptVoiceProcessing} onClose={() => { setPrivacyOpen(false); setConsentRequired(false); }} />
      </section>
    );
  }

  return (
    <section className="relative flex h-full w-full overflow-hidden bg-[#123E49] font-kiosk text-white">
      <div className="absolute inset-x-0 top-0 h-1 bg-[#F0C929]" />

      {/* 화면을 보지 않는 사용자를 위한 상태 안내 (스크린리더 전용) */}
      <p aria-live="polite" className="sr-only">
        {status === "listening"
          ? "음성 인식을 시작했습니다. 목적지를 말씀해 주세요."
          : status === "loading"
            ? "경로를 조회하고 있습니다. 잠시만 기다려 주세요."
            : ""}
      </p>

      {error && (
        <div
          role="alert"
          className="absolute left-3 right-3 top-3 z-40 flex items-center gap-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm font-bold text-red-900 shadow-lg"
        >
          <AlertCircle className="size-4 shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="block">{error}</span>
            {safetyDecision?.level === "retry" && safetyDecision.reasons.length > 0 && (
              <span className="mt-1 block text-xs font-semibold text-red-800">
                {safetyDecision.reasons.join(" ")}
              </span>
            )}
          </span>
          <button type="button" onClick={resetKioskSession} aria-label="오류 닫기" title="오류 닫기" className="grid size-11 shrink-0 place-items-center rounded hover:bg-red-100">
            <X className="size-4" />
          </button>
        </div>
      )}

      <div className="mx-auto grid h-full w-full max-w-[820px] grid-cols-[minmax(0,1fr)_112px] items-center gap-4 px-5 py-5 sm:grid-cols-[minmax(0,1fr)_150px] sm:px-8 md:gap-8">
        <div className="min-w-0">
          {status === "idle" && (
            <div className="fade-enter">
              <p className="mb-1 text-xs font-extrabold text-[#F0C929]">BITBOX 길찾기</p>
              <h2 className="mb-1 text-[clamp(22px,4vw,34px)] font-black leading-tight">어디로 갈까요?</h2>
              <p className="mb-4 text-sm font-medium text-white/65">목적지를 입력하거나 마이크를 눌러 말씀해 주세요.</p>
              <DestinationSearch onSubmit={submitTextRoute} />
            </div>
          )}

          {status === "listening" && (
            <div className="fade-enter">
              <p className="mb-2 text-xs font-extrabold text-red-300">음성 인식 중</p>
              <h2 className="text-[clamp(24px,4vw,36px)] font-black leading-tight">말씀해 주세요</h2>
              <VoiceRecording transcript={transcript} />
            </div>
          )}

          {status === "starting" && (
            <div className="fade-enter" role="status" aria-live="polite">
              <p className="mb-2 text-xs font-extrabold text-[#F0C929]">마이크 준비 중</p>
              <h2 className="text-[clamp(24px,4vw,36px)] font-black leading-tight">마이크 권한을 확인하고 있습니다</h2>
              <p className="mt-2 text-sm font-medium text-white/65">잠시만 기다려 주세요.</p>
            </div>
          )}

          {status === "loading" && <VoiceLoading />}
          {status === "confirming" && confirmation && (
            <VoiceConfirmation
              confirmation={confirmation}
              transcript={transcript}
              audioBase64={audioBase64}
              safetyDecision={safetyDecision}
              onSelect={(place) => void confirmPlace(place)}
              onRetry={requestRecording}
            />
          )}
        </div>

        <div className="flex flex-col items-center gap-2">
          {status !== "confirming" && <VoiceMicButton status={status} onClick={toggleRecording} />}
          <span className="text-center text-xs font-bold text-white/65">
            {status === "idle" ? "음성으로 찾기" : status === "starting" ? "권한 확인 중" : status === "listening" ? "눌러서 완료" : status === "confirming" ? "후보를 선택하세요" : "조회 중"}
          </span>
          <button type="button" onClick={() => { setConsentRequired(false); setPrivacyOpen(true); }} aria-label="개인정보 처리 안내" title="개인정보 처리 안내" className="grid size-11 place-items-center rounded text-white/55 hover:bg-white/10 hover:text-white">
            <ShieldCheck className="size-4" />
          </button>
        </div>
      </div>

      <PrivacyNotice open={privacyOpen} consentRequired={consentRequired} onAccept={acceptVoiceProcessing} onClose={() => { setPrivacyOpen(false); setConsentRequired(false); }} />
    </section>
  );
}
