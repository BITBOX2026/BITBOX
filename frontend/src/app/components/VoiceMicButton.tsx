import { AudioLines, Loader2, Mic } from "lucide-react";

function WaveBar({ delay }: { delay: number }) {
  return (
    <span
      className="h-7 w-1 rounded-full bg-white"
      style={{ animation: "voiceWave 0.9s ease-in-out infinite", animationDelay: `${delay}ms` }}
    />
  );
}

export function VoiceMicButton({ status, onClick }: { status: string; onClick: () => void }) {
  const isListening = status === "listening";
  const isLoading = status === "loading";
  const label = isListening ? "음성 입력 완료" : isLoading ? "경로 조회 중" : "음성 입력 시작";

  return (
    <div className="relative grid size-24 place-items-center sm:size-28">
      {isListening && (
        <div className="absolute inset-x-0 flex items-center justify-between px-1" aria-hidden="true">
          <div className="flex gap-1">{[0, 120, 240].map((delay) => <WaveBar key={delay} delay={delay} />)}</div>
          <div className="flex gap-1">{[180, 60, 300].map((delay) => <WaveBar key={delay} delay={delay} />)}</div>
        </div>
      )}

      <button
        type="button"
        onClick={onClick}
        disabled={isLoading}
        aria-label={label}
        title={label}
        className={`relative z-10 grid size-20 place-items-center rounded-full border-4 shadow-xl transition-transform focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white/35 sm:size-24 ${
          isListening
            ? "border-red-200 bg-red-600 text-white active:scale-95"
            : isLoading
              ? "cursor-wait border-white/20 bg-white/10 text-white"
              : "border-white bg-[#F0C929] text-[#17343B] hover:scale-105 active:scale-95"
        }`}
      >
        {isLoading ? (
          <Loader2 className="size-9 animate-spin" />
        ) : isListening ? (
          <AudioLines className="size-9" />
        ) : (
          <Mic className="size-9" strokeWidth={2.4} />
        )}
      </button>
    </div>
  );
}
