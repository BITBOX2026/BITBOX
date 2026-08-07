import { AlertCircle, X } from "lucide-react";
import { DestinationSearch } from "./DestinationSearch";
import { VoiceLoading } from "./VoiceLoading";
import { VoiceMicButton } from "./VoiceMicButton";
import { VoiceRecording, useVoiceRecorder } from "./VoiceRecording";
import { VoiceResult } from "./VoiceResult";

export function VoiceAssistant() {
  const {
    status,
    transcript,
    destination,
    buses,
    message,
    audioBase64,
    error,
    startRecording,
    stopRecording,
    submitTextRoute,
    reset,
  } = useVoiceRecorder();

  const toggleRecording = () => {
    if (status === "idle") void startRecording();
    if (status === "listening") stopRecording();
  };

  if (status === "result") {
    return (
      <VoiceResult
        destination={destination}
        buses={buses}
        message={message}
        audio_base64={audioBase64}
        onReset={() => void startRecording()}
        onGoHome={reset}
      />
    );
  }

  return (
    <section className="relative flex h-full w-full overflow-hidden bg-[#123E49] font-['Noto_Sans_KR'] text-white">
      <div className="absolute inset-x-0 top-0 h-1 bg-[#F0C929]" />

      {error && (
        <div
          role="alert"
          className="absolute left-3 right-3 top-3 z-40 flex items-center gap-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm font-bold text-red-900 shadow-lg"
        >
          <AlertCircle className="size-4 shrink-0" />
          <span className="min-w-0 flex-1">{error}</span>
          <button type="button" onClick={reset} aria-label="오류 닫기" title="오류 닫기" className="grid size-7 shrink-0 place-items-center rounded hover:bg-red-100">
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

          {status === "loading" && <VoiceLoading />}
        </div>

        <div className="flex flex-col items-center gap-2">
          <VoiceMicButton status={status} onClick={toggleRecording} />
          <span className="text-center text-xs font-bold text-white/65">
            {status === "idle" ? "음성으로 찾기" : status === "listening" ? "눌러서 완료" : "조회 중"}
          </span>
        </div>
      </div>
    </section>
  );
}
