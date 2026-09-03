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
  const isStarting = status === "starting";
  const isLoading = status === "loading" || isStarting;
  const label = isListening ? "음성 입력 완료" : isStarting ? "마이크 준비 중" : isLoading ? "경로 조회 중" : "음성 입력 시작";

  // 마이크 크기는 화면 **높이**를 보고 정합니다.
  //
  // 이 칸에는 버튼만 있는 것이 아니라 "음성으로 찾기" 라벨과 보호 아이콘이 함께
  // 쌓입니다. 1280x720 키오스크에서는 이 묶음이 이미 188px 이고 쓸 수 있는 높이가
  // 190px 이라, 버튼을 키우면 그대로 넘칩니다(실제로 30px 넘쳤습니다). 반대로 세로로
  // 긴 화면에서는 아래 영역이 270~430px 씩 비어 있었습니다.
  //
  // 구간은 서로 겹치지 않게 씁니다. 겹치면 어느 규칙이 이길지가 생성된 CSS 순서에
  // 달리는데, 실제로 1414px 화면에서 중간 단계가 큰 단계를 덮었습니다.
  //
  // 그래서 폭이 아니라 높이 기준으로 키웁니다. 여유가 있는 화면에서만 커지고,
  // 낮은 화면에서는 종전 크기를 지켜 아무것도 잘리지 않습니다. 손이 떨리는
  // 이용자에게는 조작 목표가 클수록 유리합니다.
  return (
    <div className="relative grid size-24 place-items-center sm:size-28 [@media(min-height:800px)_and_(max-height:999px)]:size-32 [@media(min-height:1000px)]:size-44">
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
        className={`relative z-10 grid size-20 place-items-center rounded-full border-4 shadow-xl transition-transform focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white/35 sm:size-24 [@media(min-height:800px)_and_(max-height:999px)]:size-28 [@media(min-height:1000px)]:size-40 ${
          isListening
            ? "border-red-200 bg-red-600 text-white active:scale-95"
            : isLoading
              ? "cursor-wait border-white/20 bg-white/10 text-white"
              : "border-white bg-[#F0C929] text-[#17343B] hover:scale-105 active:scale-95"
        }`}
      >
        {isLoading ? (
          <Loader2 className="size-9 animate-spin [@media(min-height:1000px)]:size-12" />
        ) : isListening ? (
          <AudioLines className="size-9 [@media(min-height:1000px)]:size-12" />
        ) : (
          <Mic className="size-9 [@media(min-height:1000px)]:size-12" strokeWidth={2.4} />
        )}
      </button>
    </div>
  );
}
