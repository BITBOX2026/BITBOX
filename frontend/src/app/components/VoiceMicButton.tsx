import { Mic, Loader2 } from "lucide-react";

// 말할 때 움직이는 막대기(음파) 컴포넌트
function WaveBar({ height, delay }: { height: number; delay: number }) {
  return (
    <div
      style={{
        width: 6,
        height: height,
        backgroundColor: "white",
        borderRadius: 3,
        animation: `voiceWave 1s ease-in-out infinite`,
        animationDelay: `${delay}ms`,
      }}
    />
  );
}

export function VoiceMicButton({ status, onClick }: { status: string; onClick: () => void }) {
  const isIdle = status === "idle";
  const isListening = status === "listening";
  const isLoading = status === "loading";

  return (
    <div className="relative flex items-center justify-center size-36">
      {/* 1. 대기 상태 펄스 (잔잔하게 퍼지는 흰색 원) */}
      {isIdle && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="absolute size-36 rounded-full bg-white/10 animate-[micPing_2s_ease-out_infinite]" />
          <div className="absolute size-28 rounded-full bg-white/15 animate-[micPing_2s_ease-out_infinite_0.5s]" />
        </div>
      )}

      {/* 2. 인식 중 상태 (빨간색 강조 및 좌우 음파 바) */}
      {isListening && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="absolute size-44 rounded-full bg-red-500/20 animate-[micPing_1s_ease-out_infinite]" />
          <div className="absolute size-36 rounded-full bg-red-500/30 animate-[micPulse_1s_ease-in-out_infinite]" />
          
          {/* 왼쪽 음파 바 */}
          <div className="absolute right-[calc(50%+70px)] flex gap-1.5">
            {[24, 40, 28, 36].map((h, i) => <WaveBar key={i} delay={i * 90} height={h} />)}
          </div>
          {/* 오른쪽 음파 바 */}
          <div className="absolute left-[calc(50%+70px)] flex gap-1.5">
            {[32, 22, 42, 26].map((h, i) => <WaveBar key={i} delay={i * 80 + 40} height={h} />)}
          </div>
        </div>
      )}

      {/* 3. 메인 버튼:  로딩 효과 및 3D 카드 뒤집기(Flip) 효과 적용 */}
      <button
        onClick={onClick}
        disabled={isLoading}
        className={`relative z-20 size-28 rounded-full flex items-center justify-center shadow-2xl 
          [transform-style:preserve-3d] transition-all duration-700 ease-in-out 
          ${isListening ? "bg-gradient-to-br from-[#DC2626] to-[#EF4444] [transform:rotateY(180deg)] shadow-[0_8px_30px_rgba(239,68,68,0.6)]" 
          : isIdle ? "bg-gradient-to-br from-white to-[#F0F4FF] [transform:rotateY(0deg)] shadow-[0_8px_30px_rgba(0,0,0,0.35)]"
          : "bg-indigo-900/50 backdrop-blur-md border border-white/20 scale-95"}`}
      >
        {/* 버튼이 뒤집힐 때 아이콘도 반대로 뒤집어서 정면을 바라보게 처리 */}
        <div className={`transition-transform duration-700 ease-in-out flex items-center justify-center p-2 ${isListening ? "[transform:rotateY(-180deg)]" : ""}`}>
          {isLoading ? <Loader2 className="size-12 text-white animate-spin" /> 
          : <Mic className={`size-14 ${isListening ? "text-white animate-[micPulse_1s_infinite]" : "text-[#2E7D32]"}`} strokeWidth={2.2} />}
        </div>
      </button>
    </div>
  );
}